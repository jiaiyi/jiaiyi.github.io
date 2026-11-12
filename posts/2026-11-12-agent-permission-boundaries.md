---
title: 给 Agent 划权限边界：全局只读、目录隔离、人工审批
date: 2026-11-12
tags: [Agent, 权限, LangGraph, AI]
summary: 在 system prompt 里写「不要删数据库」不是权限，只是建议。真正管用的是三档边界：全局只读、目录隔离、高危动作前挂起等人批。
---

先说一个结论：**在 system prompt 里写「不要删除数据库表」，不是权限，只是建议。** 模型完全可以合理地把你的话理解成「这次用户明确要求了，那就删」，然后删掉。

权限必须是**代码层面的强制约束** —— 模型看不到规则也得遵守。下面是三档可以叠加的边界，都用 `deepagents` + LangGraph 实现。

<!--more-->

## 一档：全局只读

最粗暴也最常用的一档。整个工作区能读，一个字节都不许写：

```python
agent = create_deep_agent(
    model=llm,
    backend=FilesystemBackend(root_dir="./backend_dir"),
    permissions=[
        FilesystemPermission(
            operations=["write"],
            paths=["/**"],
            mode="deny",
        )
    ],
)
```

只 deny `write`，`read` 不写就在允许列表里 —— 于是这个 Agent 变成一个**只能看不能动**的分析器：能读日志、读配置、读代码，改不了任何东西。

适合：代码审查、日志排查、只读的知识库问答。

## 二档：目录隔离

只让它在指定子目录里读写，其余全部拒绝：

```python
permissions=[
    FilesystemPermission(
        operations=["read", "write"],
        paths=["/allow_dir/**"],
        mode="allow",
    ),
    FilesystemPermission(
        operations=["read", "write"],
        paths=["/**"],
        mode="deny",
    ),
]
```

**两条规则的顺序不能反。** 写法上是「先给窄的开口，再用通配兜底拒绝」：具体路径的 allow 在前，`/**` 的 deny 在后。反过来写，第一条 deny 就把整个工作区封死了，后面那条 allow 等于没写。

这一档的实践意义在于：**Agent 的爆炸半径被限制在一个目录里**。它可以在 `/allow_dir` 下建文件、改文件、反复重写，最坏结果是这个目录变脏 —— 而 `src/`、`.git/`、`.env` 全在边界外。

适合：写代码的工具型 Agent、生成报告、批量改文档。

## 三档：高危动作前挂起等人批

前两档管的是「能碰哪些文件」，但有些工具本身就危险 —— 删表、发消息、调支付接口。这类不能靠路径拦，要靠**中断**：

```python
main_agent = create_deep_agent(
    model=llm,
    tools=[delete_table, delete_file, query_table],
    interrupt_on={
        "query_table": False,                                    # 查询放开
        "delete_table": True,                                    # 高危，全量审批
        "delete_file": {"allowed_decisions": ["approve", "reject"]},
    },
    checkpointer=MemorySaver(),   # 中断前必须能存状态
)
```

三个细节决定它能不能真的跑起来：

**① 必须有 checkpointer。** `interrupt` 的本质是保存现场然后返回。没有 `MemorySaver()`，挂起之后没有状态可恢复，恢复时会重新从头跑一遍。

**② 两次调用必须是同一个 `thread_id`。**

```python
config = {"configurable": {"thread_id": "abc"}}

result = main_agent.invoke({"messages": [...]}, config=config)   # 第一次：跑到高危动作挂起
# ... 人工决策 ...
result2 = main_agent.invoke(
    Command(resume={"decisions": decisions}),                     # 第二次：只带决策，不再重复提问
    config=config,                                                # 同一个 thread_id
)
```

第二次调用**不要再传用户的问题**，只传 `Command(resume=...)`。传了就变成新一轮对话，之前挂起的现场白存了。

**③ 一次调用里可能有多个高危动作，决策要按名字一一对应。**

```python
action_requests = result["__interrupt__"][0].value["action_requests"]
decisions = []
for item in action_requests:
    if item["name"] == "delete_table":
        decisions.append({"type": "approve"})
    elif item["name"] == "delete_file":
        decisions.append({"type": "reject"})
```

用户说「先查一下 product 表，再删 user 表，最后删掉 xxx.txt」—— 这一句话会在同一次执行里触发三个工具，前两个需要审批。**决策数组的顺序必须和 `action_requests` 一致**，所以按 `name` 匹配，不要按下标硬写。

另外 `allowed_decisions` 只给 `["approve", "reject"]` 时，这一档就**不支持 edit** —— 用户只能同意或拒绝，不能改参数。删表这种动作，改参数没有意义，砍掉 edit 反而是对的。

## 怎么选

| 动作性质 | 用哪一档 |
|---|---|
| 纯读（查日志、读代码、检索） | 一档，甚至不设边界 |
| 写但不破坏（生成报告、改草稿） | 二档，限定目录 |
| 不可逆（删表、删文件、发送、支付） | 三档，必须人工批 |
| 影响外部系统 | 三档 + 幂等键 |

判断标准只有一条：**出错了能不能撤销。** 能撤销的，边界放宽到目录就够；不能撤销的，一律挂起等人。

## 一个容易忽略的点

三档不是互斥的，是叠加的。一个真实的生产 Agent 通常是：**目录隔离（二档）+ 高危工具审批（三档）** —— 它只能在 `/workspace` 里折腾，但即使在 `/workspace` 里想删文件，也要人点头。

先划边界，再让它干活。反过来的顺序，迟早要还。

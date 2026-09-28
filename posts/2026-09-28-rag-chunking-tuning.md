---
title: RAG 切片调优：先诊断，别先调参
date: 2026-09-28
tags: [RAG, 检索, 中文处理, 向量数据库]
summary: 检索回来的是半句话、或者召回一堆只有一个标题的空片段 —— 这种问题调 chunk_size 之前，得先量出来它到底有多碎。凭感觉调参只会来回打转。
---

RAG 效果不好时，最想去调的就是 `chunk_size`。但**切片质量问题只有看真实数据才暴露** —— 凭感觉把小改大、大改小，来回试几轮也很难收敛。

正确顺序是：**先量，再改，然后验证。**

<!--more-->

## 一、先诊断：三个指标定位问题

离线跑一段，不落盘、不进向量库：

```python
import re

H = re.compile(r"^#{1,6}\s+.*$")          # markdown 标题行

def body(t):
    """去掉标题行后的正文。

    ⚠️ 必须先剔标题再数字数 —— 否则「标题自己成了一条切片」这种情况
    会被算成有内容，得不到正确判断。
    """
    return "\n".join(
        l for l in (t or "").split("\n") if not H.match(l.strip())
    ).strip()

lens = sorted(len(body(c["content"])) for c in chunks)
print(f"切片数 {len(chunks)} | 正文 最短 {lens[0]} / 中位 {lens[len(lens)//2]} / 最长 {lens[-1]}")
print(f"正文<30字碎片: {sum(1 for b in lens if b < 30)} 条")
```

**中文技术讲义的健康区间**：

| 指标 | 健康区间 | 异常说明 |
|---|---|---|
| 正文中位 | 150~400 字 | <100 → 切太碎，上下文不足 |
| 正文 <30 字占比 | 0% | >10% → 存在「纯标题碎片」 |
| 正文最长 | ≤ chunk_size | 明显小于 → 大段被腰斩 |
| 最短切片 | >0 | =0 → 就是纯标题碎片 |

### 「纯标题碎片」是怎么来的

它长这样：

```
'# 高等数学'
```

**根因**：切分器把标题行也放进了内容缓冲（`current_lines = [line]`）。当某个标题下面**紧跟另一个标题、中间没有正文**时，就切出一个只有标题的片。

这种片段会被向量化、占库，**检索时可能被召回到零信息片段** —— 用户拿到一个标题，什么答案都组织不出来。

必须丢掉。但要在切分逻辑里丢，不是事后清理。

---

## 二、三层切分：标题栈 → 二次切分 → 碎片过滤

### ① 标题栈（维护层级，同时产出 chapter / parent）

平切法只能得到「无层级的段落列表」。要拿到 `chapter`（所属章）和 `parent_title`（父标题），必须按 `#` 的数量维护一个栈：

```python
stack = []                       # [{"level": int, "text": str}, ...]

# 遇到标题 level 时：
while stack and stack[-1]["level"] >= level:   # 把不可能成为祖先的弹掉
    stack.pop()

current_parent  = stack[-1]["text"] if stack else ""    # 父标题
current_chapter = stack[0]["text"]  if stack else text  # 栈底 = 顶级章节
stack.append({"level": level, "text": text})
```

两个关键点：

- **`parent` 取 `stack[-1]`，`chapter` 取 `stack[0]`**
- 跨章时栈会被弹空 → `parent` 自然变成空字符串，**这是正确行为**，不用特殊处理

> ⚠️ **代码块里的 `#` 会被误判成标题** —— Python 注释就是以 `#` 开头的！
> 必须先用 ` ``` ` / `~~~` 的围栏状态机屏蔽掉。实测过有些课程文档的代码行**没有任何样式**，
> 只有 `Consolas` 字体，所以靠样式名判断也会漏。这个坑只有跑真实文档才发现。

### ② 二次切分（控制块大小）

```python
RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", "！", "；", " "],   # ★ 中文标点要进来
)
```

**中文技术讲义建议 `chunk_size = 500~800`，`overlap ≈ chunk_size / 6`。**

`200` 是英文短文本项目的惯性值。中文 200 字**只够装一两句话**，技术解释会被切碎 —— 检索回来的是半截，反而误导模型。

### ③ 碎片过滤（顺序很重要：先过滤，再编号）

```python
sub_chunks = splitter.split_text(chunk["content"])

kept = [sc for sc in sub_chunks if len(body(sc)) >= MIN_CHUNK_BODY_CHARS]   # ★ 先过滤
if not kept:
    logger.warning(f"「{chunk['title']}」下没有有效正文，已跳过该小节")
    continue

has_multi = len(kept) > 1                       # ★ 用过滤后的长度判断

for idx, sc in enumerate(kept, start=1):        # ★ 编号基于 kept，保证 _N 不跳号
    title = f"{chunk['title']}_{idx}" if has_multi else chunk["title"]
```

`MIN_CHUNK_BODY_CHARS = 30` 是个好起点。

**「先过滤再编号」这条不能反** —— 否则会出现 `doc_1 / doc_3 / doc_7` 这种跳号，下游看到会以为数据缺失。

### 实测效果

一份中文讲义，`chunk_size` 从 200 改到 600 并加上过滤之后：

| | 改前 | 改后 |
|---|---|---|
| 切片数 | 55 | 29 |
| 碎片率 | 21% | 0% |
| 正文中位 | 100 | 147 |
| 正文最长 | 189 | 454 |

---

## 三、改参数 = 旧数据全部作废

这一点必须先想清楚：**`chunk_size` 等常量一改，库里已切好的切片和后续新导入的就天然不一致了。**

两种处理方式：

- **导入按幂等键（如 `item_name`）先删后插** → 只需重导受影响的文档，不用清库
- 否则只能**整库清空，按新参数统一重导**

👉 **结论：趁库里数据少的时候就把切分参数定死。** 等全量灌进去再改，等于白跑一遍。

---

## 四、落库后校验：区分「切分对」和「写对了」

**离线一致 ≠ 落库一致**，必须查库复核：

```python
rows, off = [], 0
while True:                                    # ★ 分页 query 计数
    b = c.query(collection_name=NAME,
                filter="chunk_id > 0",
                output_fields=["item_name", "chapter_name", "title", "content"],
                limit=500, offset=off)
    if not b:
        break
    rows += b
    off += len(b)
    if len(b) < 500:
        break
```

**核数一律用 `query` 分页计数，不要用 `row_count` / `num_entities`。** 后者包含「已删除但未 compact」的旧行，会偏高 —— 我实测过一次删除后 `num_entities` 显示 865，真实只有 829。

复核四项：

1. `chapter_name` 的有值率
2. 层级序列是否逐级递进、跨章时清空
3. 零碎片
4. 正文长度分布是否落在健康区间

---

## 五、三个常见误判

**① 幂等键的取值和你以为的不一样。**
按错的名字去查会得到 0 条，看起来像「数据根本没进去」。查库之前先列一遍实际取值。

**② 过滤阈值调太大。**
把 `MIN_CHUNK_BODY_CHARS` 提到 100 以上，会连正常的短小节一起丢掉。**30~50 足够挡住纯标题碎片**。

**③ 只看切片数变少就以为变好了。**
片数减少可能是「碎片被丢掉」（好事），也可能是「大段被合并成一片」（要看情况）。**必须同时看正文中位长度和碎片率** —— 单看一个数字会被骗。

---

## 小结

| 步骤 | 做什么 |
|---|---|
| 1. 诊断 | 量出中位长度、碎片率、最长/最短 —— 别凭感觉 |
| 2. 切分 | 标题栈管层级 → 二次切分控大小 → **先过滤再编号** |
| 3. 参数 | 中文技术文 `chunk_size` 500~800，别沿用英文项目的 200 |
| 4. 定稿 | 库里数据少时就定死，改一次全库作废 |
| 5. 校验 | 用 `query` 分页计数（不是 `row_count`），查四项指标 |

**核心一句**：切片质量是**量**出来的，不是**调**出来的。

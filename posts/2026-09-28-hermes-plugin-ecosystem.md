---
title: Hermes 的五套「插件」根本不是一回事
date: 2026-09-28
tags: [Hermes, 插件系统, 工具链]
summary: 装上插件却不生效、改了配置没反应 —— 大多数时候是因为把五套互不相干的扩展机制混为一谈了。先分清是哪一类，再看对应的开关。
---

在 Hermes 里折腾插件，最容易遇到的困惑是：

**「我明明装上了，为什么没生效？」**

原因通常是：Hermes 的「插件」**不是一个东西，而是五套互不相干的扩展机制**。混为一谈就会一直在错的开关上打转。

<!--more-->

## 先分清五类扩展面

| 类别 | 位置 | 开关 |
|---|---|---|
| ① 常驻 hook / tool 插件 | `hermes-agent/plugins/` | `plugins.enabled` 白名单 |
| ② Provider 型插件 | `plugins/memory/`、`model-providers/`、`web/` 等 | 各自目录独立发现，**同类同时只激活一个** |
| ③ 平台网关 | `plugins/platforms/` | `config.yaml` 的 `platform_toolsets` + 各自凭据 |
| ④ Dashboard 插件 | 自带 `dashboard/manifest.json` | **自动挂载，不受白名单控制** |
| ⑤ MCP | `optional-mcps/` | `config.yaml` 的 `mcp_servers` |

几个容易搞混的点：

**① 和 ④ 的开关完全相反。** hook 插件要显式 `enable`；dashboard 插件只要你把目录放对，它自己就挂上了 —— 反过来，你在白名单里写它的名字也没用。

**③ 是「平台网关」不是「插件」**。telegram / discord / 飞书 / 钉钉 / 企业微信这些走的是平台通道，和 `plugins.enabled` 没关系。

**⑤ 压根不是 Python 插件**。MCP 是独立协议，配置项在 `mcp_servers` 下。你去 `plugins.enabled` 里找它当然找不到。

---

## 目录布局

路径都相对于 `HERMES_HOME`：

| 项 | 路径 |
|---|---|
| 源码 / 仓库 | `%HERMES_HOME%\hermes-agent` |
| 内置插件 | `%HERMES_HOME%\hermes-agent\plugins\` |
| 用户插件 | `%HERMES_HOME%\plugins\` |
| 桌面端插件 | `%HERMES_HOME%\desktop-plugins\` |
| 启用白名单 | `%HERMES_HOME%\config.yaml` → `plugins.enabled` |
| venv | `%HERMES_HOME%\hermes-agent\venv` |
| 官方文档 | `...\hermes-agent\website\docs\user-guide\features\` |

`HERMES_HOME` 的解析顺序：**先读环境变量，读不到才去注册表读用户环境变量** —— 所以从资源管理器（而不是 shell）启动时，也能拿到正确的 home。

---

## 两个已知的坑

### 坑一：远端插件索引已经失效

源码里 `hermes_cli/plugin_index.py` 指向的是：

```
https://raw.githubusercontent.com/NousResearch/hermes-plugin-index/main/index.json
```

**实测该仓库 404** → `hermes plugins install <短名>` 这条路走不通。

只能直连仓库：

```bash
hermes plugins install owner/repo [--ref <sha>] [--enable|--no-enable]
```

本地那份种子索引 `hermes_cli/data/plugin_index.json` 也只有寥寥几条，基本指望不上。

### 坑二：有些插件在 Windows 上根本跑不起来

某些插件的 `plugin.yaml` 里写着：

```yaml
platforms: [linux, macos]
```

**Windows 上装了也起不来。**

所以判断「这个插件能不能用」，**第一件事是看 `plugin.yaml` 的 `platforms` 字段** —— 别等装完了发现不生效才回去查。

---

## 另外三个反直觉的点

**① 内置插件全部 opt-in，永不自动启用。**

升级 Hermes 也不会替你打开。**装了 ≠ 开了。**

**② 目录里没有 `plugin.yaml`，不等于它不是插件。**

`context_engine/`、`hermes-achievements/`、`kanban/` 走的是**独立发现路径**。
另外 `memory/` 和 `context_engine/` 还被**显式排除**在 bundled 扫描之外 —— 所以按「遍历所有 plugin.yaml」去盘点，会漏掉它们。

**③ 用户插件和内置插件同名时，用户版胜出（last-writer-wins）。**

这可以拿来**覆盖内置实现**，是个有用的特性。

---

## 盘点脚本：注意 YAML 折叠块

遍历所有 manifest 提取 name / kind / description —— 这里有个细节：`description: >` 这种**折叠块**，用朴素正则 `^key: (.+)$` 只能抓到 `>` 本身。

```python
import os, re, json

ROOT = os.path.join(os.environ["HERMES_HOME"], "hermes-agent", "plugins")

def parse_yaml_lite(path):
    """极简 YAML 解析，重点处理 > / | 这类折叠块"""
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    out, i = {}, 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", lines[i])
        if m:
            k, v = m.group(1), m.group(2).strip()
            if v in (">", ">-", "|", "|-", ">+", "|+"):
                buf, i = [], i + 1
                while i < len(lines) and (lines[i].startswith((" ", "\t"))
                                          or not lines[i].strip()):
                    buf.append(lines[i].strip())
                    i += 1
                out[k] = " ".join(x for x in buf if x)
                continue
            out[k] = v.strip('"').strip("'")
        i += 1
    return out

for dp, _, fs in os.walk(ROOT):
    if "plugin.yaml" in fs:
        info = parse_yaml_lite(os.path.join(dp, "plugin.yaml"))
        info["path"] = os.path.relpath(dp, ROOT).replace("\\", "/")
        print(json.dumps(info, ensure_ascii=False))
```

---

## 常用命令

```bash
hermes plugins                 # 交互式勾选 UI
hermes plugins list            # 列出全部（标注 bundled / user 来源）
hermes plugins enable <name>
hermes plugins disable <name>
hermes memory setup|status|off
hermes tools                   # 交互式
```

配置式等价写法（`%HERMES_HOME%\config.yaml`）：

```yaml
plugins:
  enabled:
    - disk-cleanup
    - security-guidance
memory:
  provider: holographic
```

---

## 哪些值得开（带判断，不是罗列）

**`disk-cleanup`** —— hook 驱动，零配置。关键在于它**只在 `HERMES_HOME` 和 `/tmp/hermes-*` 内动手**，白名单保住 `logs/ sessions/ memories/ cron/ cache/ skills/ plugins/`，而且删之前有 `dry-run`。安全性足够，可以直接开。

**`security-guidance`** —— 25 条规则（`pickle.load` / `eval` / `shell=True` / XXE / SRI / CI 注入…）。默认是 **warn 不 block**，误报不误事。**写代码场景收益最高。**

**`observability/langfuse`** —— 要算 token / 成本 / 工具调用账的时候开。它是 fail-open 的，坏了也不影响主循环，所以可以放心装。

**记忆后端**：`holographic` 是本地 SQLite + FTS5，**零依赖零费用**。`mem0` / `supermemory` / `honcho` 都要 key 或者联网。

**搜索后端**：`web-ddgs` 免 key（`pip install ddgs`）最省事；国内环境更适合自建 `web-searxng`。

---

## 小结

遇到「插件不生效」时，先问三个问题：

1. **它属于五类里的哪一类？**（决定去哪个开关找）
2. **`plugin.yaml` 里的 `platforms` 包含当前系统吗？**
3. **它是不是 dashboard 型（不需要白名单）或者压根是 MCP（不在这里配）？**

把这三问答清楚，大部分「装了没用」的问题就自己解开了。

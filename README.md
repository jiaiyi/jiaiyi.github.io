# 甲乙的技术笔记

一个零框架的静态博客。写 Markdown，跑一个脚本，push 就发布。

站点地址：https://jiaiyi.github.io

---

## 为什么不用现成框架

内容只有 Markdown 一种，读者只关心能不能打开、读起来舒不舒服。
引入一套前端框架意味着：依赖会过期、构建会变慢、某天需要为升级折腾半天。

这个博客只有 **两个 Python 依赖**（`markdown` + `pygments`），全文渲染逻辑在一个
不到 200 行的 `build.py` 里，随时可以自己改。

## 目录结构

```
blog/
├── build.py            构建脚本（唯一的代码）
├── posts/              文章源文件（Markdown + frontmatter）
├── templates/          HTML 模板
│   ├── base.html       页面骨架
│   └── card.html       列表页的文章卡片
├── static/
│   └── style.css       样式
└── docs/               构建产物（提交进仓库，GitHub Pages 发布它）
```

## 环境准备

```bash
pip install markdown pygments
```

## 写一篇新文章

在 `posts/` 下新建 `YYYY-MM-DD-英文短名.md`：

```markdown
---
title: 文章标题
date: 2026-09-17
tags: [标签一, 标签二]
summary: 一句话摘要，显示在列表页
---

正文开头（列表页会显示 `<!--more-->` 之前的部分）……

<!--more-->

后面的内容只在文章详情页出现。
```

`<!--more-->` 是可选的。不加的话，列表页摘要会直接用 frontmatter 里的 `summary`。

## 构建与预览

```bash
python build.py              # 构建到 docs/
python build.py --serve      # 构建后起本地服务 http://127.0.0.1:8899
```

## 发布

```bash
python build.py
git add -A
git commit -m "post: 新文章标题"
git push
```

GitHub Pages 需要在仓库设置里把 Source 设为 **main 分支 / docs 目录**（只需配一次）。

## 已发布的文章

| 日期 | 标题 |
|---|---|
| 2026-09-17 | 装完 PyTorch 发现 GPU 用不上？先看看你装的是不是 CPU 版 |
| 2026-09-17 | Milvus 报 code=1100？两类 schema 里看不出来的约束 |

## 相关

配套的 Agent Skills 仓库：[jiaiyi/agent-skills](https://github.com/jiaiyi/agent-skills)

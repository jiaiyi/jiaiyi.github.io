#!/usr/bin/env python3
"""把 posts/*.md 转成适合发到 CSDN 的版本。

与博客原文的差异：
  1. 去掉 `<!--more-->` 标记 —— CSDN 用自己的「阅读全文」分隔机制，
     留着这个注释会原样显示出来
  2. 文末追加原文链接与博客地址 —— 平台分发的主要目的就是导流回自己站点
  3. 输出到 csdn/，并生成一份发布清单（含标签、分类建议）

用法：
    python make_csdn.py
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "posts"
OUT = ROOT / "csdn"

SITE = "https://jiaiyi.github.io"

# CSDN 要求 3-5 个标签。按原文 frontmatter 的 tags 映射，
# 补充一些平台侧更常被检索的词。
TAG_EXTRA = {
    "wsl-proxy": ["Linux", "环境配置"],
    "windows-locked-folder": ["文件管理", "经验分享"],
    "docx-ooxml-pitfalls": ["Python", "文档处理"],
    "pytorch-cpu-wheel": ["深度学习", "环境配置"],
    "milvus-code-1100": ["向量数据库", "RAG"],
}

# CSDN 发文的「分类专栏」建议
CATEGORY = {
    "wsl-proxy": "开发环境",
    "windows-locked-folder": "Windows 踩坑",
    "docx-ooxml-pitfalls": "Python 实战",
    "pytorch-cpu-wheel": "深度学习环境",
    "milvus-code-1100": "向量数据库",
}


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw, body = text[3:end], text[end + 4:].lstrip("\n")

    meta: dict = {}
    for line in raw.strip("\n").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value.strip("\"'")
    return meta, body


def build_one(src: Path) -> dict:
    meta, body = parse_front_matter(src.read_text(encoding="utf-8"))
    slug = src.stem.split("-", 3)[-1] if re.match(r"\d{4}-\d{2}-\d{2}-", src.stem) else src.stem

    # 1. 去掉 more 标记（连同可能的空行）
    body = re.sub(r"\n*<!--more-->\n*", "\n\n", body).strip() + "\n"

    # 2. 文末导流
    body += (
        "\n---\n\n"
        f"> 原文地址：{SITE}/posts/{slug}.html\n"
        f">\n"
        f"> 更多同类文章见我的博客：{SITE}\n"
    )

    title = meta.get("title", src.stem)
    tags = list(meta.get("tags") or [])
    tags += TAG_EXTRA.get(slug, [])
    # 去重保序
    seen, merged = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            merged.append(t)

    (OUT / f"{slug}.md").write_text(body, encoding="utf-8")
    return {
        "slug": slug,
        "title": title,
        "tags": merged[:5],
        "category": CATEGORY.get(slug, "技术分享"),
        "summary": meta.get("summary", ""),
        "url": f"{SITE}/posts/{slug}.html",
        "chars": len(body),
    }


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    items = [build_one(p) for p in sorted(POSTS.glob("*.md"))]

    lines = [
        "# CSDN 发布清单",
        "",
        f"共 {len(items)} 篇。源文件在本目录，按下面的元信息粘贴即可。",
        "",
        "## 发布步骤",
        "",
        "1. 打开 https://blog.csdn.net/qq_mp/write （或点「写文章」）",
        "2. 标题、标签、分类按下表填",
        "3. `csdn/<slug>.md` 的内容**整体复制**粘贴进正文区（编辑器支持 Markdown）",
        "4. 确认预览无误后点「发布文章」",
        "",
        "> 文中若含代码块，粘贴后检查一下缩进是否保留；CSDN 的 Markdown 模式偶尔会吞掉围栏。",
        "",
        "---",
        "",
    ]

    for i, it in enumerate(items, 1):
        lines += [
            f"## {i}. {it['title']}",
            "",
            f"- **标题**：`{it['title']}`",
            f"- **标签**：{'、'.join(it['tags'])}",
            f"- **分类专栏**：{it['category']}",
            f"- **正文文件**：`csdn/{it['slug']}.md`（{it['chars']} 字符）",
            f"- **原文链接**：{it['url']}",
            "",
            f"摘要：{it['summary']}",
            "",
        ]

    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"已生成 {len(items)} 篇 CSDN 版本 → {OUT}")
    for it in items:
        print(f"  · {it['title']}")
        print(f"      标签: {'、'.join(it['tags'])}   专栏: {it['category']}")


if __name__ == "__main__":
    main()

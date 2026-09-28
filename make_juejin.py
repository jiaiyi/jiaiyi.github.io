#!/usr/bin/env python3
"""把 posts/*.md 转成适合发到掘金的版本，并生成发布清单。

掘金与博客原文的差异：
  1. 去掉 `<!--more-->`（掘金用自己的摘要字段，不留这个注释）
  2. 文末追加原文链接 —— 平台分发的核心目的是导流回自己站点
  3. **掘金对摘要长度有硬要求：50~100 字**，超了会被拒
     脚本会检查并标出不合格的
  4. 掘金分类只有固定八类，需要从文章主题映射过去

用法:
    python make_juejin.py
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "posts"
OUT = ROOT / "juejin"
SITE = "https://jiaiyi.github.io"

# 掘金的固定分类（八类），按文章主题映射
CATEGORY = {
    "milvus-code-1100":              "后端",
    "pytorch-cpu-wheel":             "人工智能",
    "docx-ooxml-pitfalls":           "后端",
    "windows-locked-folder":         "开发工具",
    "wsl-proxy":                     "开发工具",
    "electron-launch-verify":        "前端",
    "frontend-verification-without-framework": "前端",
    "git-auth-and-repo-hygiene":     "开发工具",
    "git-cannot-reach-github":       "开发工具",
    "github-pages-pitfalls":         "开发工具",
    "hermes-plugin-ecosystem":       "开发工具",
    "pycharm-uv-interpreter":        "开发工具",
    "rag-chunking-tuning":           "人工智能",
    "rag-retrieval-routing":         "人工智能",
}

# 掘金侧更常被检索的补充标签
TAG_EXTRA = {
    "milvus-code-1100":        ["向量数据库"],
    "pytorch-cpu-wheel":       ["深度学习"],
    "docx-ooxml-pitfalls":     ["Python"],
    "windows-locked-folder":   ["Windows"],
    "wsl-proxy":               ["Linux"],
    "electron-launch-verify":  ["Electron"],
    "rag-chunking-tuning":     ["RAG"],
    "rag-retrieval-routing":   ["RAG"],
}

MIN_BRIEF, MAX_BRIEF = 50, 100


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
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k] = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k] = v.strip("\"'")
    return meta, body


def brief_len(s: str) -> int:
    """掘金按字符数算，标点和空格一般不计入，这里按去掉空白后的长度估。"""
    return len(re.sub(r"\s+", "", s))


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    items = []
    for p in sorted(POSTS.glob("*.md")):
        meta, body = parse_front_matter(p.read_text(encoding="utf-8"))
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", p.stem)

        # 1. 去掉 more 标记
        body = re.sub(r"\n*<!--more-->\n*", "\n\n", body).strip() + "\n"

        # 2. 文末导流
        body += (
            "\n---\n\n"
            f"> 原文地址：{SITE}/posts/{slug}.html\n"
            f">\n"
            f"> 更多同类文章见我的博客：{SITE}\n"
        )
        (OUT / f"{slug}.md").write_text(body, encoding="utf-8")

        title = meta.get("title", p.stem)
        brief = meta.get("summary", "")
        n = brief_len(brief)

        tags = list(meta.get("tags") or [])
        if isinstance(tags, str):
            tags = [tags]
        tags += TAG_EXTRA.get(slug, [])
        seen, merged = set(), []
        for t in tags:
            if t not in seen:
                seen.add(t)
                merged.append(t)

        items.append({
            "slug": slug,
            "title": title,
            "brief": brief,
            "n": n,
            "ok": MIN_BRIEF <= n <= MAX_BRIEF,
            "category": CATEGORY.get(slug, "开发工具"),
            "tags": merged[:5],
            "url": f"{SITE}/posts/{slug}.html",
        })

    # ---------------- 清单 ----------------
    bad = [it for it in items if not it["ok"]]
    lines = [
        "# 掘金发布清单",
        "",
        f"共 {len(items)} 篇。**摘要必须在 50~100 字之间**，否则创建草稿会失败。",
        "",
    ]
    if bad:
        lines += [
            f"## ⚠️ 摘要长度不合格（{len(bad)} 篇，发布前先改）",
            "",
            "| 文章 | 当前字数 | 问题 |",
            "|---|---|---|",
        ]
        for it in bad:
            lines.append(
                f"| {it['title']} | {it['n']} | {'太短' if it['n'] < MIN_BRIEF else '太长'} |"
            )
        lines.append("")
        lines.append("修法：改 `posts/<文件>.md` 里 frontmatter 的 `summary` 字段。")
        lines.append("")

    lines += [
        "## 发布方式",
        "",
        "**手动（推荐先用这个试水）**",
        "1. 打开 https://juejin.cn/editor/drafts/new",
        "2. 标题、分类、标签按下表填，摘要粘进「摘要」输入框",
        "3. `juejin/<slug>.md` 内容整体粘贴进正文区（编辑器支持 Markdown）",
        "4. 发布",
        "",
        "**自动（走掘金开放接口）**",
        "```",
        "POST https://api.juejin.cn/content_api/v1/article_draft/create",
        "POST https://api.juejin.cn/content_api/v1/article/publish",
        "鉴权：Cookie（sessionid + passport_csrf_token）",
        "```",
        "",
        "---",
        "",
    ]

    for i, it in enumerate(items, 1):
        flag = "" if it["ok"] else f"  ⚠️ 摘要 {it['n']} 字，需调整"
        lines += [
            f"## {i}. {it['title']}{flag}",
            "",
            f"- **标题**：`{it['title']}`",
            f"- **分类**：{it['category']}",
            f"- **标签**：{'、'.join(it['tags'])}",
            f"- **摘要**（{it['n']} 字）：{it['brief']}",
            f"- **正文文件**：`juejin/{it['slug']}.md`",
            f"- **原文链接**：{it['url']}",
            "",
        ]

    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"已生成 {len(items)} 篇掘金版本 → {OUT}")
    print(f"  摘要合格 {len(items) - len(bad)} 篇，不合格 {len(bad)} 篇")
    for it in items:
        mark = "✓" if it["ok"] else "⚠"
        print(f"  {mark} {it['title'][:36]:<38} 摘要{it['n']:>4}字  {it['category']}")


if __name__ == "__main__":
    main()

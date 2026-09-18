#!/usr/bin/env python3
"""极简静态博客生成器 —— 零框架，只依赖 markdown + pygments。

用法:
    python build.py            # 构建到 docs/
    python build.py --serve    # 构建后起本地预览服务

文章放在 posts/*.md，开头是 frontmatter:

    ---
    title: 标题
    date: 2026-09-17
    tags: [Windows, 工具链]
    summary: 一句话摘要，显示在列表页
    ---

正文里 `<!--more-->` 之后的内容不会出现在列表页摘要中。
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import markdown
    import pygments
    from pygments.formatters import HtmlFormatter
except ImportError:  # pragma: no cover
    sys.exit("缺少依赖，先装：pip install markdown pygments")

ROOT = Path(__file__).resolve().parent
POSTS_DIR = ROOT / "posts"
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUT_DIR = ROOT / "docs"      # GitHub Pages 从 main 分支的 /docs 目录发布

# ---------------------------------------------------------------- 站点配置
SITE = {
    "title": "甲乙的技术笔记",
    "tagline": "真实踩过的坑，比文档有用",
    "description": "Windows 工具链、RAG 检索、向量库与 AI 编码助手的实战踩坑记录。",
    "author": "甲乙",
    "github": "https://github.com/jiaiyi",
    "repo": "https://github.com/jiaiyi/agent-skills",
    "base_url": "https://jiaiyi.github.io",
    "lang": "zh-CN",
}

MD = markdown.Markdown(
    extensions=["extra", "codehilite", "toc", "sane_lists", "admonition"],
    extension_configs={
        "codehilite": {"css_class": "codehilite", "guess_lang": False, "linenums": False},
        "toc": {"permalink": False},
    },
    output_format="html5",
)


# ---------------------------------------------------------------- 工具函数
def parse_front_matter(text: str) -> tuple[dict, str]:
    """解析开头被 --- 包住的键值对。列表支持 `[a, b]` 与多行 `- a` 两种写法。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    raw = text[3:end].strip("\n")
    body = text[end + 4 :].lstrip("\n")

    meta: dict = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        # 多行列表项
        if line.lstrip().startswith("- ") and current_key:
            meta.setdefault(current_key, [])
            if isinstance(meta[current_key], list):
                meta[current_key].append(line.lstrip()[2:].strip().strip("\"'"))
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        current_key = key
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
        elif value in ("", "|", ">"):
            meta[key] = [] if value == "" else ""
        else:
            meta[key] = value.strip("\"'")
    return meta, body


def slugify(name: str) -> str:
    """文件名转 URL：保留中文与字母数字，其余压成连字符。"""
    name = name.lower()
    name = re.sub(r"[^\w\u4e00-\u9fff]+", "-", name, flags=re.UNICODE)
    return name.strip("-")


def render(template: str, **kw) -> str:
    out = template
    for k, v in kw.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def fmt_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)


def read(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 文章加载
class Post:
    def __init__(self, path: Path):
        self.path = path
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        self.meta = meta
        self.body_md = body
        self.title = meta.get("title") or path.stem
        self.date = meta.get("date") or ""
        self.tags = meta.get("tags") or []
        if isinstance(self.tags, str):
            self.tags = [self.tags]
        self.summary = meta.get("summary") or ""
        self.draft = str(meta.get("draft", "")).lower() in ("true", "yes", "1")
        # 文件名前缀的日期，如 2026-09-17-xxx.md
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)", path.stem)
        self.date_part, self.slug_part = (m.group(1), m.group(2)) if m else (self.date, path.stem)
        self.slug = slugify(self.slug_part)
        self.url = f"posts/{self.slug}.html"

    def render_body(self) -> tuple[str, str]:
        """返回 (整篇 HTML, 列表页用的摘要 HTML)。"""
        MD.reset()
        full = MD.convert(self.body_md)
        head = self.body_md.split("<!--more-->")[0]
        MD.reset()
        excerpt = MD.convert(head) if head != self.body_md else ""
        return full, excerpt


# ---------------------------------------------------------------- 页面生成
def build(site: dict) -> list[Post]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "posts").mkdir(exist_ok=True)
    (OUT_DIR / "static").mkdir(exist_ok=True)

    posts = [Post(p) for p in sorted(POSTS_DIR.glob("*.md"))]
    posts = [p for p in posts if not p.draft]
    posts.sort(key=lambda p: (p.date_part, p.slug_part), reverse=True)

    base = read("base.html")
    card_tpl = read("card.html")

    cards = []
    for p in posts:
        _, excerpt = p.render_body()
        if not excerpt:
            excerpt = f"<p>{html.escape(p.summary)}</p>" if p.summary else ""
        tag_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in p.tags)
        cards.append(
            render(
                card_tpl,
                url=p.url,
                title=html.escape(p.title),
                date=fmt_date(p.date_part),
                tags=tag_html,
                summary=excerpt,
            )
        )

    # ---- 列表页
    list_html = "\n".join(cards) or '<p class="empty">还没有文章。</p>'
    index_html = _page(
        base,
        lang=site["lang"],
        page_title=site["title"],
        description=site["description"],
        body_class="page-index",
        content=f"""
<header class="hero">
  <h1>{html.escape(site["title"])}</h1>
  <p class="tagline">{html.escape(site["tagline"])}</p>
  <p class="desc">{html.escape(site["description"])}</p>
  <p class="links">
    <a href="{site["repo"]}">skill 仓库</a>
    <span class="sep">·</span>
    <a href="{site["github"]}">GitHub</a>
    <span class="sep">·</span>
    <a href="feed.xml">RSS</a>
  </p>
</header>
<section class="post-list">
{list_html}
</section>""",
    )
    (OUT_DIR / "index.html").write_text(index_html, encoding="utf-8")

    # ---- 文章页
    for p in posts:
        body, _ = p.render_body()
        tag_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in p.tags)
        page = _page(
            base,
            lang=site["lang"],
            page_title=f"{p.title} · {site['title']}",
            description=html.escape(p.summary or p.title),
            body_class="page-post",
            content=f"""
<article class="post">
  <a class="back" href="../index.html">← 返回列表</a>
  <h1>{html.escape(p.title)}</h1>
  <div class="meta"><time>{fmt_date(p.date_part)}</time>{tag_html}</div>
  <div class="content">{body}</div>
</article>""",
        )
        (OUT_DIR / p.url).write_text(page, encoding="utf-8")

    # ---- RSS
    (OUT_DIR / "feed.xml").write_text(_rss(site, posts), encoding="utf-8")

    # ---- 静态资源
    if STATIC_DIR.exists():
        for f in STATIC_DIR.iterdir():
            if f.is_file():
                shutil.copy2(f, OUT_DIR / "static" / f.name)
    (OUT_DIR / "static" / "pygments.css").write_text(
        HtmlFormatter().get_style_defs(".codehilite"), encoding="utf-8"
    )
    # GitHub Pages 默认会跑 Jekyll 处理，那会把仓库根目录的 README 当首页、
    # 并忽略下划线开头的文件。站点是预构建好的纯静态文件，直接跳过它。
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    return posts


def _page(base: str, *, lang, page_title, description, body_class, content) -> str:
    return render(
        base,
        lang=lang,
        page_title=html.escape(page_title),
        description=description,
        body_class=body_class,
        content=content,
        site_title=html.escape(SITE["title"]),
        repo=SITE["repo"],
        github=SITE["github"],
        year=datetime.now().year,
    )


def _rss(site: dict, posts: list[Post]) -> str:
    items = []
    for p in posts[:20]:
        items.append(
            f"""  <item>
    <title>{html.escape(p.title)}</title>
    <link>{site['base_url']}/{p.url}</link>
    <guid>{site['base_url']}/{p.url}</guid>
    <description>{html.escape(p.summary)}</description>
  </item>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{html.escape(site['title'])}</title>
  <link>{site['base_url']}</link>
  <description>{html.escape(site['description'])}</description>
{chr(10).join(items)}
</channel>
</rss>
"""


def serve(port: int = 8899) -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(OUT_DIR))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"预览地址 http://127.0.0.1:{port}/")
        httpd.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="构建后启动本地预览")
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()

    built = build(SITE)
    print(f"构建完成：{len(built)} 篇文章 → {OUT_DIR}")
    for p in built:
        print(f"  · {p.title}")
    if args.serve:
        serve(args.port)

#!/usr/bin/env python3
"""把 csdn/*.md 发布到 CSDN。

前置：先跑一次 `python csdn_login.py` 取得登录态。

用法:
    python csdn_publish.py --probe               # 打开编辑器并 dump 元素（首次调试）
    python csdn_publish.py --list                # 列出可发文章
    python csdn_publish.py --slug wsl-proxy           # 发布一篇
    python csdn_publish.py --slug wsl-proxy --draft   # 只存草稿
    python csdn_publish.py --all                      # 全部发布

来自社区实践的三个关键点（都已体现在代码里）：
  1. CSDN 是 Vue SPA，**不响应 JS 触发的 click()**，必须用真实鼠标事件
     —— Playwright 的 click() 本身就是真实事件，所以能用
  2. 弹窗遮罩 `mark-mask-box-div` 会拦截点击，必须先把它从 DOM 移除
  3. 编辑器是 CodeMirror，正文**必须走剪贴板 + Ctrl+V**，直接 fill/insert 无效
  另外：页面上有两个「发布文章」按钮，要点编辑区上方那个
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

from playwright.sync_api import Page, sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
CSDN_DIR = ROOT / "csdn"
STATE = pathlib.Path.home() / ".workbuddy" / "csdn-state.json"

EDITOR_URL = "https://mp.csdn.net/mp_blog/creation/editor"

# 每个元素给多个选择器，改版后容错
SEL = {
    "md_tab": [
        'button.nav-tab-btn:has-text("Markdown")',
        '.nav-tab-btn:has-text("Markdown")',
        'text=Markdown',
    ],
    "title": [
        'input[placeholder*="请输入文章标题"]',
        '.article-bar input[type="text"]',
        'input.title-input',
    ],
    "editor": [
        ".cledit-section",
        ".editor__inner",
        ".CodeMirror",
        "div[contenteditable='true']",
    ],
    "publish_btn": [
        'button.btn-publish:has-text("发布文章")',
        '.article-bar button:has-text("发布文章")',
        'button:has-text("发布文章")',
    ],
    "save_draft": [
        'button:has-text("存草稿")',
        'button:has-text("保存草稿")',
        '.article-bar button:has-text("草稿")',
    ],
    "tag_input": [
        '.mark_tag input',
        'input[placeholder*="标签"]',
        'input[placeholder*="搜索标签"]',
    ],
    "tag_confirm": [
        '.mark_tag button:has-text("确定")',
        'button:has-text("确定")',
    ],
    "dialog_publish": [
        '.modal button:has-text("发布文章")',
        '.el-dialog button:has-text("发布文章")',
        '.release-dialog button:has-text("发布文章")',
    ],
}

# 弹窗遮罩，会拦截点击
MASK_SELECTORS = [".mark-mask-box-div", ".mask-box-div", ".modal-mask"]


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def first_visible(page: Page, selectors: list[str], timeout: int = 10000):
    """按顺序尝试选择器，返回第一个可见的 locator。"""
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    return loc
            except Exception:
                continue
        time.sleep(0.5)
    return None


def kill_masks(page: Page) -> int:
    """移除遮罩层。返回移除数量。"""
    return page.evaluate(
        """(sels) => {
            let n = 0;
            for (const s of sels) {
                document.querySelectorAll(s).forEach(el => { el.remove(); n++; });
            }
            return n;
        }""",
        MASK_SELECTORS,
    )


def parse_meta(slug: str) -> dict:
    """从 csdn/README.md 的清单里取该篇的标题 / 标签 / 专栏。"""
    readme = (CSDN_DIR / "README.md").read_text(encoding="utf-8")
    # 找到 "## N. 标题" 到下一个 "## " 之间的块
    pattern = re.compile(r"^## \d+\.\s(.+?)$(.*?)(?=^## \d+\.|\Z)", re.M | re.S)
    for m in pattern.finditer(readme):
        block = m.group(2)
        if f"csdn/{slug}.md" not in block:
            continue
        title = m.group(1).strip()
        tags = re.search(r"\*\*标签\*\*：(.+)", block)
        cat = re.search(r"\*\*分类专栏\*\*：(.+)", block)
        return {
            "title": title,
            "tags": [t.strip() for t in tags.group(1).split("、") if t.strip()] if tags else [],
            "category": cat.group(1).strip() if cat else "",
        }
    # 兜底：拿正文第一行 #
    body = (CSDN_DIR / f"{slug}.md").read_text(encoding="utf-8")
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return {"title": m.group(1).strip() if m else slug, "tags": [], "category": ""}


def paste_body(page: Page, text: str) -> None:
    """正文走剪贴板 + Ctrl+V —— CodeMirror 只认 paste 事件。"""
    editor = first_visible(page, SEL["editor"])
    if not editor:
        raise RuntimeError("找不到正文编辑器")
    editor.click()
    time.sleep(0.5)
    page.evaluate(
        """async (t) => { await navigator.clipboard.writeText(t); }""",
        text,
    )
    time.sleep(0.4)
    page.keyboard.press("Control+v")
    time.sleep(2.5)


def set_tags(page: Page, tags: list[str]) -> None:
    if not tags:
        return
    box = first_visible(page, SEL["tag_input"], timeout=6000)
    if not box:
        log(f"⚠ 未找到标签输入框，请手动补标签：{'、'.join(tags)}")
        return
    for t in tags:
        try:
            box.click()
            box.fill("")
            box.type(t, delay=60)
            time.sleep(1.2)
            page.keyboard.press("Enter")
            time.sleep(0.8)
        except Exception as e:
            log(f"⚠ 标签「{t}」设置失败：{e}")


def publish_one(page: Page, slug: str, draft: bool) -> bool:
    meta = parse_meta(slug)
    body_file = CSDN_DIR / f"{slug}.md"
    body = body_file.read_text(encoding="utf-8")

    print(f"\n▶ {meta['title']}")
    log(f"标签：{'、'.join(meta['tags']) or '(无)'}")

    page.goto(EDITOR_URL, wait_until="domcontentloaded")
    time.sleep(4)

    if "passport.csdn.net" in page.url:
        log("✗ 登录态已失效，请重新运行 csdn_login.py")
        return False

    # 1. 切 Markdown 模式
    tab = first_visible(page, SEL["md_tab"], timeout=8000)
    if tab:
        tab.click()
        time.sleep(1.5)
        log("已切到 Markdown 模式")

    time.sleep(1)
    removed = kill_masks(page)
    if removed:
        log(f"移除遮罩层 {removed} 个")

    # 2. 标题
    title_box = first_visible(page, SEL["title"], timeout=10000)
    if not title_box:
        log("✗ 找不到标题输入框，页面结构可能已改版")
        return False
    title_box.click()
    title_box.fill(meta["title"])
    time.sleep(0.8)
    log(f"标题已填：{meta['title']}")

    # 3. 正文
    paste_body(page, body)
    log(f"正文已粘贴（{len(body)} 字符）")

    # 4. 发布 / 存草稿
    btn_key = "save_draft" if draft else "publish_btn"
    btn = first_visible(page, SEL[btn_key], timeout=8000)
    if not btn:
        log(f"✗ 找不到「{'存草稿' if draft else '发布文章'}」按钮")
        log("  已在浏览器里保留现场，请手动完成；或按 Ctrl+C 退出")
        time.sleep(120)
        return False

    btn.click()
    time.sleep(2.5)
    kill_masks(page)

    # 标签在发布弹窗里
    set_tags(page, meta["tags"])

    if draft:
        log("已点存草稿")
    else:
        # 弹窗里的确认按钮
        confirm = first_visible(page, SEL["dialog_publish"], timeout=8000)
        if confirm:
            confirm.click()
            time.sleep(3)
            log("已点发布")
        else:
            log("⚠ 未找到弹窗内的发布按钮，请在浏览器里手动确认")

    time.sleep(3)
    log(f"完成，当前页面：{page.url}")
    return True


def probe(page: Page) -> None:
    """打开编辑器，dump 真实 DOM 结构，用于定位元素。"""
    msgs: list[str] = []
    page.on("console", lambda m: msgs.append(f"{m.type}: {m.text[:120]}"))
    page.on("pageerror", lambda e: msgs.append(f"pageerror: {str(e)[:120]}"))

    # ⚠️ domcontentloaded 等不到（编辑器依赖太重）；commit + 等关键元素更稳
    page.goto(EDITOR_URL, wait_until="commit", timeout=60000)

    print("等待编辑器渲染…")
    ready = False
    for sel in [".article-bar", ".cledit-section", "input[placeholder*='标题']",
                ".editor__inner", "[contenteditable='true']"]:
        try:
            page.wait_for_selector(sel, timeout=25000, state="attached")
            print(f"  ✓ 出现元素：{sel}")
            ready = True
            break
        except Exception:
            print(f"  …未出现：{sel}")
    if not ready:
        print("  ⚠️ 关键元素都没出现，继续 dump 现状")

    time.sleep(3)
    print(f"\n当前 URL：{page.url}")

    print("\n=== 页面 HTML 长度 ===")
    print(f"  {len(page.content())} 字符（空应用约几百字符）")

    print("\n=== #appMain 子元素数 ===")
    print(f"  {page.evaluate('() => (document.querySelector(\"#appMain\")||{}).children?.length ?? -1')}")

    print("\n=== console 消息（前 15 条）===")
    for m in msgs[:15]:
        print(f"  {m}")
    if not msgs:
        print("  （无）")

    print("\n=== 可输入元素 ===")
    print(page.evaluate(
        """() => {
            let out = '';
            document.querySelectorAll('input, textarea, [contenteditable="true"]').forEach(e => {
                const cls = (typeof e.className === 'string') ? e.className.slice(0,50) : '';
                out += e.tagName.toLowerCase()
                     + ' | ph=' + (e.placeholder || '')
                     + ' | cls=' + cls
                     + ' | vis=' + !!(e.offsetWidth || e.offsetHeight) + '\\n';
            });
            return out || '（无）';
        }"""
    )[:1800])

    print("\n=== 按钮（前 20 个）===")
    btns = page.locator("button").all()
    print(f"  共 {len(btns)} 个")
    for b in btns[:20]:
        try:
            t = (b.inner_text() or "").strip().replace("\n", " ")[:22]
            c = (b.get_attribute("class") or "")[:52]
            if t:
                print(f"  [{t:<22}] {c}")
        except Exception:
            pass

    # 用 CDP 截图，绕开 Playwright 的「等字体加载」阻塞
    shot = ROOT / "_shots" / "csdn-editor.png"
    shot.parent.mkdir(exist_ok=True)
    try:
        cdp = page.context.new_cdp_session(page)
        result = cdp.send("Page.captureScreenshot", {"format": "png"})
        import base64
        shot.write_bytes(base64.b64decode(result["data"]))
        print(f"\n已截图（CDP） → {shot}")
    except Exception as e:
        print(f"\n截图失败：{e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="dump 编辑器元素（首次调试）")
    ap.add_argument("--list", action="store_true", help="列出可发文章")
    ap.add_argument("--slug", help="发布指定文件（不含 .md）")
    ap.add_argument("--all", action="store_true", help="发布全部")
    ap.add_argument("--draft", action="store_true", help="只存草稿，不发布")
    args = ap.parse_args()

    slugs = sorted(p.stem for p in CSDN_DIR.glob("*.md") if p.name != "README.md")

    if args.list:
        print(f"可发文章（共 {len(slugs)} 篇）：")
        for s in slugs:
            m = parse_meta(s)
            print(f"  {s:<28} {m['title']}  [{('、'.join(m['tags']))}]")
        return

    if not STATE.exists():
        print(f"✗ 未找到登录态 {STATE}")
        print("  请先运行：python csdn_login.py")
        sys.exit(1)

    targets = slugs if args.all else ([args.slug] if args.slug else [])
    if not targets and not args.probe:
        print("请指定 --slug <名称> 或 --all（用 --list 查看可选项）")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        ctx = browser.new_context(
            storage_state=str(STATE),
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        ctx.grant_permissions(
            ["clipboard-read", "clipboard-write"], origin="https://mp.csdn.net"
        )
        page = ctx.new_page()

        if args.probe:
            probe(page)
        else:
            for s in targets:
                try:
                    publish_one(page, s, args.draft)
                except Exception as e:
                    log(f"✗ {s} 失败：{e}")
                time.sleep(3)

        browser.close()


if __name__ == "__main__":
    main()

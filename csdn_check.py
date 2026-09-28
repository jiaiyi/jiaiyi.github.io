#!/usr/bin/env python3
"""严格诊断 CSDN 登录态 —— 别再用「元素存在」判断，要看可见性和页面真实内容。

之前的误判：`.passport-login-container` 在 DOM 中始终存在（可能是隐藏的骨架），
用 `.count() > 0` 判断会把已登录也判成未登录。
正确做法是 `.is_visible()` + 看页面关键文案。

用法:
    python csdn_check.py
"""

from __future__ import annotations

import pathlib
import time

from playwright.sync_api import sync_playwright

PROFILE = pathlib.Path.home() / ".workbuddy/csdn-profile"
STATE = pathlib.Path.home() / ".workbuddy/csdn-state.json"
EDITOR = "https://mp.csdn.net/mp_blog/creation/editor"
HOME = "https://www.csdn.net/"


def main() -> None:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            args=["--no-first-run", "--no-default-browser-check", "--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        try:
            print("=" * 62)
            print("① 打开编辑器（跳过首页 —— CSDN 首页资源太重，goto 容易超时）")
            page.goto(EDITOR, wait_until="domcontentloaded", timeout=90000)
            time.sleep(8)
            print(f"   URL: {page.url}")

            # 关键：看登录框是否**可见**，而不是是否存在
            box = page.locator(".passport-login-container")
            n = box.count()
            vis = False
            if n:
                try:
                    vis = box.first.is_visible()
                except Exception:
                    vis = False
            print(f"   .passport-login-container  存在={n}  可见={vis}")

            # 看页面里有没有编辑器才有的元素
            editor_hits = {}
            for sel in [".cledit-section", ".editor__inner", ".CodeMirror",
                        "input[placeholder*='标题']", "button:has-text('发布文章')",
                        "button:has-text('保存')", ".article-bar"]:
                try:
                    c = page.locator(sel).count()
                    v = page.locator(sel).first.is_visible() if c else False
                    editor_hits[sel] = (c, v)
                except Exception:
                    editor_hits[sel] = (-1, False)
            print("   编辑器元素：")
            for sel, (c, v) in editor_hits.items():
                print(f"     {sel:<34} 存在={c:<3} 可见={v}")

            # 页面可见文本前 300 字
            body = page.inner_text("body")
            snippet = " / ".join(x.strip() for x in body.splitlines() if x.strip())[:300]
            print(f"\n③ 页面可见文本片段：\n   {snippet}")

            shot = pathlib.Path(r"C:\Users\Administrator\blog\_shots\csdn-check.png")
            shot.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(shot))
            print(f"\n④ 截图 → {shot}")

            # 结论
            logged = (not vis) and any(v for _, v in editor_hits.values())
            print("\n" + "=" * 62)
            if logged:
                print("✓ 判定：已登录（登录框不可见，且编辑器元素可见）")
                ctx.storage_state(path=str(STATE))
                print(f"  已刷新 state → {STATE}")
            else:
                print("✗ 判定：未登录（登录框可见 或 编辑器元素不可见）")
            print("=" * 62)

            time.sleep(3)
        finally:
            ctx.close()


if __name__ == "__main__":
    main()

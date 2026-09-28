#!/usr/bin/env python3
"""CSDN 登录（落在自动化专用 profile 里，不影响你自己的 Chrome）。

用持久化 profile（~/.workbuddy/csdn-profile），所以：
  · 登录一次之后长期有效，不需要每次登录
  · profile 是独立的，你可以同时正常使用自己的 Chrome
  · 登录产生的 cookie + localStorage 都存在这个 profile 里

用法:
    python csdn_login.py

流程：
    打开浏览器 → 你在窗口里扫码登录 → 脚本自动检测并保存 →
    之后用 csdn_publish.py 直接发文
"""

from __future__ import annotations

import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

PROFILE = pathlib.Path.home() / ".workbuddy/csdn-profile"
STATE = pathlib.Path.home() / ".workbuddy/csdn-state.json"

LOGIN_URL = "https://passport.csdn.net/login"
# 登录成功后要能访问的页面
CHECK_URL = "https://mp.csdn.net/mp_blog/creation/editor"


def still_logged_out(page) -> bool:
    """未登录判定。

    ⚠️ 不能用「元素是否存在」判断 —— `.passport-login-container` 在 DOM 里
    始终存在（骨架节点），已登录时只是被隐藏。必须看 is_visible()。
    """
    if "passport.csdn.net" in page.url:
        return True
    try:
        box = page.locator(".passport-login-container")
        if box.count() > 0 and box.first.is_visible():
            return True
    except Exception:
        pass
    return False


def main() -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)

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
            # 先看看是不是已经登录了
            page.goto(CHECK_URL, wait_until="domcontentloaded", timeout=90000)
            time.sleep(5)
            if not still_logged_out(page):
                print("✓ 该 profile 已经处于登录状态，无需重新登录")
            else:
                print("=" * 64)
                print("请在打开的浏览器窗口里登录 CSDN（扫码或账号密码都行）")
                print("登录成功后脚本会自动继续，最多等 10 分钟。")
                print("=" * 64)
                page.goto(LOGIN_URL, wait_until="domcontentloaded")
                time.sleep(2)

                deadline = time.time() + 600
                ok = False
                while time.time() < deadline:
                    time.sleep(4)
                    try:
                        if "passport.csdn.net" not in page.url and "csdn.net" in page.url:
                            # 再确认一次
                            page.goto(CHECK_URL, wait_until="domcontentloaded", timeout=60000)
                            time.sleep(4)
                            if not still_logged_out(page):
                                ok = True
                                break
                    except Exception:
                        continue
                    if int(deadline - time.time()) % 30 < 4:
                        print(f"  …等待登录（剩 {int(deadline - time.time())} 秒）")

                if not ok:
                    print("✗ 超时未检测到登录成功，请重跑本脚本。")
                    sys.exit(1)

            ctx.storage_state(path=str(STATE))
            cookies = ctx.cookies()
            csdn = [c for c in cookies if "csdn" in c.get("domain", "")]
            print(f"\n✓ 登录成功")
            print(f"  profile : {PROFILE}")
            print(f"  state   : {STATE}")
            print(f"  cookie  : 共 {len(cookies)} 条，CSDN 相关 {len(csdn)} 条")
            print("\n下一步：python csdn_publish.py --list  然后发布")
        finally:
            ctx.close()


if __name__ == "__main__":
    main()

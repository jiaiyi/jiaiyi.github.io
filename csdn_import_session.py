#!/usr/bin/env python3
"""从本机 Chrome 的登录态导出 CSDN 会话（一次性）。

踩过的三个坑（记在这里，免得下次重复试）：

  1. **Chrome 运行时独占锁定 Cookie 数据库**
     用 CreateFileW 带 SHARE_READ|WRITE|DELETE 也是 err=32 (SHARING_VIOLATION)
     → 必须先完全关闭 Chrome

  2. **Chrome 禁止在默认数据目录上开远程调试**
     `DevTools remote debugging requires a non-default data directory`
     → 所以 launch_persistent_context(user_data_dir=真实profile) 必然超时失败

  3. **整个 profile 有 900MB，不值得整体复制**
     → 实测只需 4 个文件（约 670KB）就能带走登录态：
        Local State                  解密密钥（DPAPI / app-bound key）
        Default/Network/Cookies      cookie 本体
        Default/Preferences          站点设置
        Default/Secure Preferences
     用**同一个 Chrome 二进制**启动时密钥仍能解开 —— app-bound key 绑定的是
     Chrome 安装路径，不随 profile 目录变化。

用法:
    python csdn_import_session.py
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

SRC = pathlib.Path.home() / "AppData/Local/Google/Chrome/User Data"
DEST = pathlib.Path.home() / ".workbuddy/csdn-profile"
STATE = pathlib.Path.home() / ".workbuddy/csdn-state.json"

WANTED_FILES = [
    "Local State",
    "Default/Network/Cookies",
    "Default/Preferences",
    "Default/Secure Preferences",
]

# ★ 关键：CSDN 的登录凭证**不只在 cookie 里**
#   首次复制时只带了 cookie，结果编辑器页仍然弹出 iframe 登录框
#   （DOM 里出现 div.passport-login-container）。localStorage 必须一起带。
WANTED_DIRS = [
    "Default/Local Storage",
    "Default/Session Storage",
]

CHECK_URL = "https://mp.csdn.net/mp_blog/manage/article"


def chrome_count() -> int:
    try:
        out = subprocess.run(
            ["tasklist", "/fi", "imagename eq chrome.exe", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=20,
            encoding="gbk", errors="replace",
        ).stdout
    except Exception:
        return -1
    return sum(1 for ln in out.splitlines() if "chrome.exe" in ln.lower())


def wait_chrome_closed(timeout: int = 240) -> bool:
    print("=" * 64)
    print("需要 Chrome 完全关闭（脚本自动检测，最多等 4 分钟）")
    print("=" * 64)
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = chrome_count()
        if n == 0:
            print("✓ Chrome 已退出")
            return True
        print(f"  …Chrome 仍在运行（{n} 个进程），剩 {int(deadline - time.time())} 秒")
        time.sleep(4)
    return False


def copy_profile() -> int:
    total = 0
    for rel in WANTED_FILES:
        s = SRC / rel
        if not s.exists():
            print(f"  跳过（不存在）: {rel}")
            continue
        d = DEST / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        # 带上预写日志，否则最新 cookie 可能还没落主库
        for ext in ("-wal", "-shm"):
            p = pathlib.Path(str(s) + ext)
            if p.exists():
                shutil.copy2(p, pathlib.Path(str(d) + ext))
        total += d.stat().st_size
        print(f"  已复制 {rel:<34} {d.stat().st_size:>8} B")

    for rel in WANTED_DIRS:
        s = SRC / rel
        if not s.exists():
            print(f"  跳过（不存在）: {rel}")
            continue
        d = DEST / rel
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(s, d)
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        total += size
        print(f"  已复制 {rel:<34} {size:>8} B  [目录]")
    return total


def main() -> None:
    if not SRC.exists():
        print(f"✗ 找不到 Chrome 配置目录：{SRC}")
        sys.exit(1)

    if not wait_chrome_closed():
        print("✗ 等待超时，请关闭 Chrome 后重试。")
        sys.exit(1)

    time.sleep(2)

    if DEST.exists():
        shutil.rmtree(DEST)
    print(f"\n复制关键文件 → {DEST}")
    total = copy_profile()
    print(f"  合计 {total / 1024:.0f} KB（整个 profile 约 900 MB）")

    print("\n启动浏览器（会弹窗口，用的是复制出来的配置）…")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(DEST),
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            args=["--no-first-run", "--no-default-browser-check", "--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(CHECK_URL, wait_until="domcontentloaded", timeout=90000)
            time.sleep(6)
            print(f"  当前地址：{page.url}")

            # 光看 URL 不够 —— 未登录时页面可能仍停在 mp.csdn.net，
            # 但在 DOM 里插入 iframe 登录框（.passport-login-container）
            has_login_box = page.locator(".passport-login-container").count() > 0
            print(f"  是否出现登录框：{'是' if has_login_box else '否'}")

            if "passport.csdn.net" in page.url or has_login_box:
                print("\n✗ 未登录（被弹回登录页）—— cookie 没带过来。")
                print("  窗口还开着，你可以在里面手动登录，登录完它会自动继续。")
                # 给用户一个在这窗口里补救登录的机会
                deadline = time.time() + 180
                while time.time() < deadline:
                    time.sleep(5)
                    if "passport.csdn.net" not in page.url:
                        break
                else:
                    ctx.close()
                    sys.exit(2)

            ctx.storage_state(path=str(STATE))
            cookies = ctx.cookies()
            csdn = [c for c in cookies if "csdn" in c.get("domain", "")]
            print(f"\n✓ 登录态有效，已导出 → {STATE}")
            print(f"  共 {len(cookies)} 条 cookie，CSDN 相关 {len(csdn)} 条")
            for c in csdn[:10]:
                print(f"    {c['domain']:<22} {c['name']}")
        finally:
            ctx.close()
            print("\n浏览器已关闭，可以正常开 Chrome 了。")


if __name__ == "__main__":
    main()

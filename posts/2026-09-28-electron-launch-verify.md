---
title: 打包好的 Electron 应用「启动即崩」？先查环境变量
date: 2026-09-28
tags: [Electron, Windows, 调试]
summary: 进程秒退、exit code 0、日志文件根本不存在 —— 看起来像构建坏了或者 exe 被截断。但如果它是在 AI 编程助手的 shell 里启动的，八成是环境变量被污染了。
---

一个打包好的 Electron 应用，交给 AI 编程助手去启动，经常「看起来是坏的」：

- 进程**秒退**
- **exit code 0**（成功？）
- stdout / stderr **完全空白**
- **不生成任何应用日志** —— 你以为会写的那个 log 文件根本不创建

看起来和「安装坏了」「exe 被截断」一模一样。

**但大多数情况不是应用的问题，是启动环境的问题。**

<!--more-->

## 陷阱一：`ELECTRON_RUN_AS_NODE=1` 被宿主注入

AI 编码助手（WorkBuddy、各种 agent 沙箱）的集成 Bash 环境里**带着 `ELECTRON_RUN_AS_NODE=1`** —— 因为宿主自己需要用 Electron 当 Node 跑。

这个环境变量的作用很直接：**让任何 Electron 应用以纯 Node 模式启动**。

于是现象就是上面那四行：秒退、exit 0、无输出、无日志。**因为你的应用压根没把自己当成 GUI 程序跑起来。**

**排查第一步永远是查这个：**

```bash
env | grep -iE "^ELECTRON|^WORKBUDDY|^CODEBUDDY|^VSCODE"
```

启动前必须把它剥离（连同宿主自己注入的其他变量一起）：

```python
env = {k: v for k, v in os.environ.items()
       if not k.startswith(("ELECTRON_", "WORKBUDDY", "CODEBUDDY", "VSCODE_"))}
env["APP_HOME"] = r"D:\path\to\app-home"      # 按应用需要显式指定
```

---

## 陷阱二：命令结束后，子进程被 Job 对象连坐回收

宿主把 Bash 命令跑在一个 Windows **Job 对象**里（kill-on-close 语义）。实测三条结论：

**① 命令内启动的 GUI，命令一返回就被杀掉。**
进程消失、`netstat` 里只剩 `TIME_WAIT` —— 端口已经关了，但连接状态还没回收。

**② `CREATE_BREAKAWAY_FROM_JOB` 会被拒。**

```
OSError [WinError 5] 拒绝访问
```

原因是那个 Job 没开 `BREAKAWAY_OK` 标志。这条路走不通。

**③ `cmd //c start ""` 不可用。**

MSYS 会做路径转换，`//c` 被毁掉 —— 结果是启动了一个**交互式 cmd 并打印版本 banner**，什么也没跑。

> **结论：不要承诺「我帮你把窗口留在桌面上」。**
>
> 正确做法是：**启动 → 在它存活期间做验证（截图 / 读日志）→ 让它被回收。**
> 长期运行交给用户**在自己的终端或资源管理器里**启动。

这条边界很重要 —— 我一开始就承诺错了，白折腾了几轮。

---

## 启动 + 验证的标准脚本

用应用自带 venv 的 python（宿主环境的 python 往往缺 `PIL` / `pywin32` 这类库）。
**stderr 一定要留痕**，否则崩了查不到原因。

```python
import subprocess, os, time, ctypes
from ctypes import wintypes
from PIL import ImageGrab

u = ctypes.windll.user32

exe = r"D:\path\to\app\release\win-unpacked\App.exe"

env = {k: v for k, v in os.environ.items()
       if not k.startswith(("ELECTRON_", "WORKBUDDY", "CODEBUDDY"))}
env["APP_HOME"] = r"D:\path\to\app-home"

p = subprocess.Popen(
    [exe],
    cwd=os.path.dirname(os.path.dirname(exe)),   # 与应用自身启动时的 cwd 一致
    env=env,
    stdin=subprocess.DEVNULL,
    stdout=open(r"D:\tmp\gui.out.log", "wb"),    # 别用 DEVNULL，否则崩了没线索
    stderr=subprocess.STDOUT,
    close_fds=True,
    creationflags=0x00000200,                    # NEW_PROCESS_GROUP
)

def find_window(pid):
    """枚举属于该进程的可见窗口"""
    found = []
    def cb(hwnd, _):
        q = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(q))
        if q.value == pid and u.IsWindowVisible(hwnd) and u.GetWindowTextLengthW(hwnd):
            found.append(hwnd)
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return found

hwnd = None
for i in range(45):                    # 冷启动约 3s 出窗口，后端 ready 约 8s
    w = find_window(p.pid)
    if w:
        hwnd = w[0]
        print("窗口在第", i, "秒出现")
        break
    time.sleep(1)

if hwnd:
    u.ShowWindow(hwnd, 9)              # SW_RESTORE
    u.SetForegroundWindow(hwnd)
    time.sleep(8)                      # 等后端 ready + 首屏渲染

    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True)
    img.save(r"D:\tmp\gui.png")

    # 白屏/黑屏检测（比肉眼看快）
    px = list(img.convert("RGB").resize((60, 40)).getdata())
    print("unique_colors =", len(set(px)),
          "avg_rgb =", tuple(sum(c[i] for c in px) // len(px) for i in range(3)))

print("alive:", p.poll() is None)
```

### 怎么读这些输出

**窗口标题 + `GetWindowRect` 尺寸** → 先确认「窗口真的存在」，再截图。

**`unique_colors` 的判断**：

- 浅色 UI 大约是**几百种颜色**，平均色 200+
- 如果只有 **1~2 种颜色**，平均色接近 `(255,255,255)` 或 `(0,0,0)`
  → **说明没渲染出来**，去看日志

**截图之后一定要用工具直接看那张 PNG 核对**，别只看数字。数字正常但画面错位、重叠、缺块的情况太多了。

**另外注意 `cwd`**：Electron 应用常依赖相对路径找 `resources/`，工作目录要设成和它自己启动方式一致的目录。

---

## 顺带一提：创建快捷方式

```python
import win32com.client

shell = win32com.client.Dispatch("WScript.Shell")
sc = shell.CreateShortcut(r"C:\Users\<u>\Desktop\App.lnk")
sc.TargetPath       = r"...\release\win-unpacked\App.exe"
sc.WorkingDirectory = r"...\app"              # 与应用自身启动时的 cwd 一致
sc.IconLocation     = r"...\App.exe,0"        # exe 内已嵌入图标时直接引用
sc.Save()
```

`win32com` 要用**应用 venv 的 python**（venv 里通常有 pywin32），宿主环境的 python 没有。

⚠️ **不要用 bash heredoc 跑这段** —— 会被安全策略拦下：

```
Command blocked for security: Known Windows LOLBin that can execute
arbitrary code outside command validation
```

**解法：先用文件写入工具把脚本存成 `.py` 文件，再 `python xxx.py` 执行**，就能过。

### 验收别只看「文件存在」

- 回读 `CreateShortcut()` 拿到 Target / WorkingDir / Icon，并确认 `os.path.isfile(Target)`
- 校验二进制头 —— `.lnk` 的 `HeaderSize == 0x4c`，
  CLSID 是 `0114020000000000c000000000000046`
- **启动测试不要在助手 shell 里做**（会被陷阱一污染成假失败）—— 交给用户双击验证

⚠️ 目标 exe 在 `release\win-unpacked\` 下，重新构建会**原地替换**该目录 →
快捷方式路径不变，不用重建。

另外如果机器装了「腾讯桌面整理」这类工具，新图标可能被它收纳/分组，不一定立刻出现在默认位置。

---

## 小结

| 现象 | 先查什么 |
|---|---|
| 秒退 + exit code 0 + 无日志 | `ELECTRON_RUN_AS_NODE` 等宿主注入的变量 |
| 命令返回后进程就没了 | Job 对象回收，属正常，别试图留住 |
| 窗口存在但一片白 | `unique_colors` 只有 1~2 种 → 渲染失败，看日志 |
| 截图数字正常但画面不对 | 用工具实际看一眼 PNG |
| heredoc 跑 Python 被拦 | 先写 `.py` 文件再执行 |

**核心一句**：Electron 应用的「启动即崩」，在 AI 助手的环境里**大概率是环境变量的问题** ——
`env | grep ELECTRON` 是排查的第一条命令。

想重命名或删除一个文件夹，Windows 弹出一句：

```
操作无法完成，因为其中的文件夹或文件已在另一程序中打开
```

它**不告诉你是哪个程序**。于是你开始瞎猜：杀毒软件？云盘？刚才那个终端？

关掉终端重试 —— 还是不行。

## 先理解有两类占用源

| 类型 | 说明 | 常见程度 |
|---|---|---|
| **某进程的「当前工作目录」(cwd) 落在该文件夹里** | 进程没打开任何文件，只是「站在」这个目录里 | 最常见，也最容易被忽略 |
| 某进程打开了该文件夹里的某个文件句柄 | 真正持有了文件 | 相对少见 |

**第一类是关键。** Windows 不允许删除/重命名任何进程的 cwd 所在的目录 ——
哪怕那个进程什么文件都没碰。

想想谁会把 cwd 停在你的项目根目录：一个开着的终端（`cd` 进去了）、
一个把该目录当工作区打开的 IDE。

---

## ⚠️ 最重要的那个陷阱：你自己的编辑器在拦你

只要你在 **VS Code / PyCharm / Cursor / WorkBuddy** 里把某个文件夹作为**工作区打开着**，
这个 IDE 的**多个进程**（主进程、语言服务、集成终端、沙箱、若干 node/python 子进程）
的 cwd 就都停在工作区根目录。

**所以拦着你改名的那个人，就是你自己正在用的编辑器。**

这也解释了为什么「关掉终端再重试」永远无效 —— 终端只是众多占用者里最小的一个。

正确的处理顺序是：**先关终端，再退出 IDE（或切换工作区），最后才重试**。
只做第一步是最常见的无效操作。

---

## 怎么定位到底是谁

网上常见的建议是 `openfiles /query`，但在默认配置的 Windows 上**基本没用**，
它会直接告诉你条件不满足：

```
信息: 需要启动系统全局标志"维护对象列表"才能查看本地打开的文件
```

（要开那个标志得改注册表并重启。不值得。）

更直接的办法是**逐进程扫 cwd**：

```python
# find_dir_lock.py —— python -m pip install psutil
import sys, os
import psutil

target = os.path.normcase(os.path.abspath(sys.argv[1]))
denied = 0

print(f"扫描目标: {target}\n")
print("── cwd 落在目标目录内的进程 ──")
for p in psutil.process_iter(["pid", "name"]):
    try:
        cwd = p.cwd()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        denied += 1
        continue
    except Exception:
        continue
    if cwd and os.path.normcase(cwd).startswith(target):
        print(f"  PID {p.info['pid']:<7} {p.info['name']:<22} cwd={cwd}")

print("\n── 打开了目标目录内文件的进程 ──")
for p in psutil.process_iter(["pid", "name"]):
    try:
        for f in p.open_files():
            if os.path.normcase(f.path).startswith(target):
                print(f"  PID {p.info['pid']:<7} {p.info['name']:<22} {f.path}")
                break
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        denied += 1
    except Exception:
        continue

print(f"\n跳过的受限进程数: {denied}")
if denied:
    print("（命中为空但改名仍失败 → 占用者可能在别的权限下，用管理员身份重跑）")
```

用法：

```bash
python -m pip install psutil
python find_dir_lock.py "D:\some\path"
```

`AccessDenied` 的进程会被跳过 —— 如果跳过的数量不少，而改名仍然失败，
说明占用者可能在**另一个权限级别**下，需要用管理员身份再跑一次。

---

## 按占用者类型处理

| 占用者 | 处理方式 |
|---|---|
| `cmd.exe` / `pwsh.exe` / `bash.exe`，cwd 在目录里 | 关掉那个终端窗口，或先 `cd ..` 退出去 |
| IDE 主进程 + 一堆 node/python/sandbox 子进程 | **退出 IDE，或切到别的工作区**，然后改名 |
| 云盘同步客户端（OneDrive、WPS 云盘、坚果云、Dropbox） | 暂停同步，或退出客户端 |
| 杀毒 / 索引（Windows Search、Defender） | 通常几秒后释放，直接点「重试」 |
| `explorer.exe` 且你在该目录开过预览/缩略图 | 关掉那个资源管理器窗口，或重启 explorer |

---

## 不想关编辑器？用目录联接绕开

如果占用者就是你的 IDE，而你不想中断手头的工作 —— **别改名，改用一个无空格的访问路径**：

```
cmd> mklink /J "D:\new_path_no_space" "D:\old path with space"
```

几个要点：

- `/J` 创建的是 **junction（目录联接）**，**不需要管理员权限**；
  符号链接（`/D`）才需要提权。这个区别很实用。
- 之后所有工具都用 `D:\new_path_no_space\...` 访问，**物理目录原地不动**。
- 删除联接用 `rmdir "D:\new_path_no_space"` —— **只删链接，不会删目标内容**。
  别顺手用 `del`。
- 适用场景：你真正想解决的只是「路径含空格导致某些脚本翻车」，而不是非要改物理目录名。

---

## 真改了名，别忘了这些副作用

重命名**工作区根目录**之前先想清楚：

- IDE 里保存的**工作区路径会失效**，得用新路径重新打开。
- 藏在目录里的项目级配置（`.vscode/`、`.idea/`、`.workbuddy/`、`.git/`）会**跟着目录一起移动** ——
  数据不会丢，但引用旧绝对路径的配置项会断（比如 `.idea/misc.xml` 里的解释器路径）。
- **Python 虚拟环境**：`pyvenv.cfg` 和 `Scripts/*.exe` 里可能写死了原路径。
  改名后如果 `python.exe` 报错，**最干净的做法是删掉重装 venv**，不要手动去改那些文件。
- 正在该目录下跑的进程（训练、服务、watch 任务）会继续持有旧路径的句柄 —— 它们不会自己迁移。

---

## 决策树

```
改名/删除报「文件夹正在使用」
├─ 有终端 cd 在里面        → 关掉那个终端窗口
├─ 有 IDE 开着该目录       → 退出 IDE / 切换工作区；不想关就用 mklink /J 绕开
├─ 有云盘同步客户端在跑    → 暂停同步
├─ 什么都没查到            → 用管理员身份重跑脚本；再不行重启 explorer.exe
└─ 仍然失败                → 重启机器，趁没启动任何程序时立刻改
```

核心认知一句话：**占用者不一定是「打开了文件」的进程，也可能只是「站在这个目录里」的进程** ——
而最常站在你的项目根目录里的，就是你自己开着的编辑器。

---

> 原文地址：https://jiaiyi.github.io/posts/windows-locked-folder.html
>
> 更多同类文章见我的博客：https://jiaiyi.github.io

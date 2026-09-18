如果你在 Windows 上开了代理，浏览器一切正常，但切到 WSL 里执行 `curl` 得到的是**一片空白** ——
不是超时、不是报错，是真的一行输出都没有，连响应头都不打印。

`pip` / `uv` 的表现则是卡在第一个包上不动。

这个现象很有辨识度，值得先记住它。

## 先理解为什么会「完全没输出」

Windows 上跑的代理（Clash、mihomo 之类）默认只监听 `127.0.0.1:7890`。

而 **WSL2 默认是 NAT 模式 —— 它有自己的网络命名空间**，里面的 `127.0.0.1` 指的是
WSL 自己，不是 Windows。所以 WSL 去连 `127.0.0.1:7890` 时，那个端口在它的世界里根本
不存在。

连不上，`curl` 就静默退出 —— 这就是「没有任何输出」的来源。

WSL 自己其实会提示这一点，只是容易被忽略：

```
检测到 localhost 代理配置，但未镜像到 WSL。NAT 模式下的 WSL 不支持 localhost 代理。
```

---

## 一条命令定性

在 **Windows 侧**执行：

```bash
netstat -an | grep :7890
```

结果只有两种，对应两条不同的路：

| 输出 | 含义 | 怎么办 |
|---|---|---|
| `127.0.0.1:7890 LISTENING` | 只绑回环，**WSL 连不上** | 走解法 A 或 B |
| `0.0.0.0:7890 LISTENING` | 已放开局域网 | 只需在 WSL 里指向网关（解法 B 第 3 步） |

---

## 解法 A（推荐）：mirrored + autoProxy

WSL 的原生方案。编辑 `C:\Users\<你的用户名>\.wslconfig`：

```ini
[wsl2]
networkingMode=mirrored
autoProxy=true
```

**注意键名是 `networkingMode`（带 `ing`）。** 写成 `networkMode` 会被 WSL 判定为
「未知键」然后**静默忽略** —— 你会以为配了，实际没生效。

`mirrored` 模式下 WSL 与 Windows 共享网络接口，所以 `127.0.0.1:7890` 直接就是 Clash 的端口。

前提：**Windows 侧的系统代理必须开着** —— `autoProxy` 是从系统代理设置继承的。确认一下：

```python
import winreg

k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                   r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
for n in ("ProxyEnable", "ProxyServer", "ProxyOverride"):
    try:
        print(n, "=", winreg.QueryValueEx(k, n)[0])
    except FileNotFoundError:
        print(n, "= (未设置)")

# 期望看到:
#   ProxyEnable = 1
#   ProxyServer = '127.0.0.1:7890'
```

然后 `wsl --shutdown`，重开终端。

⚠️ **不要再手动 export 代理变量**。mirrored 模式下 `127.0.0.1:7890` 已经是正确的地址，
手动设置反而会把它指向错误的地方。

验证：

```bash
env | grep -i proxy                                    # autoProxy 会自动注入
curl -sI --max-time 10 https://pypi.org/simple/ | head -1   # 期望 HTTP/2 200
```

---

## 解法 B（NAT 模式兜底）

如果你的环境不方便开 mirrored，就得让代理监听在能被 WSL 访问的地址上。

**第 1 步：打开代理的 `allow-lan`。**

这一步有个坑：**Clash Party 界面上的开关不一定写进内核配置。** 我实测界面上打开之后，
`mihomo.yaml` 里仍然是 `false`。直接改文件更可靠：

```
%APPDATA%\mihomo-party\mihomo.yaml        # 内核实际生效的配置
%APPDATA%\mihomo-party\work\config.yaml   # 工作目录副本
```

两处都把 `allow-lan: false` 改成 `true`，然后**重启内核**才生效。

**第 2 步：确认绑定真的变了。**

```bash
netstat -an | grep :7890     # 应从 127.0.0.1 变成 0.0.0.0
```

**第 3 步：WSL 里指向网关。**

```bash
export host_ip=$(ip route show default | awk '{print $3}')
export https_proxy="http://$host_ip:7890"
export http_proxy="$https_proxy"

curl -sI --max-time 10 https://pypi.org/simple/ | head -1
```

`host_ip` 就是 Windows 上那块 `vEthernet (WSL)` 网卡的地址，形如 `172.18.128.1`。

---

## 几个容易踩的细节

- **`export` 不跨会话。** 新开一个 WSL 终端，`echo $host_ip` 就是空的 —— 变量只在当前
  会话有效。要么每次重设，要么写进 `~/.bashrc`，要么直接用解法 A 一劳永逸。
- **别用 `ping` 测代理通不通。** `PROXY` 系列环境变量只对 HTTP 客户端有效，`ping` 走的是
  ICMP，根本不经过代理 —— 你会得到一个假的「不通」。统一用 `curl -I` 验证。
- **Clash 的 `ProxyOverride` 里看到 `172.16.*~172.31.*` 不用动。** 那是自动排除
  WSL/VMware 网段用的，是对的。
- **如果 `allow-lan` 放开了还是不通**，再看一层：新版 WSL 的网卡名会带
  `(Hyper-V firewall)`，防火墙策略可能仍在拦。这时候在 Windows 侧查
  `ipconfig` 确认网段，再用 `netstat` 确认绑定、`tasklist` 确认进程是否还活着。

---

## 小结

| 现象 | 判断 |
|---|---|
| WSL 里 curl 完全无输出 | 基本可以直接锁定是代理没镜像进去 |
| Windows 侧 `netstat` 显示 `127.0.0.1:7890` | 只绑回环，WSL 天然连不上 |
| 想一劳永逸 | `.wslconfig` 用 `networkingMode=mirrored` + `autoProxy=true` |
| 不方便改模式 | 开 `allow-lan` + WSL 里指网关 IP |

关键认知就一句话：**WSL 的 `127.0.0.1` 不是 Windows 的 `127.0.0.1`。**
记住这个，这类问题能省下不少排查时间。

---

> 原文地址：https://jiaiyi.github.io/posts/wsl-proxy.html
>
> 更多同类文章见我的博客：https://jiaiyi.github.io

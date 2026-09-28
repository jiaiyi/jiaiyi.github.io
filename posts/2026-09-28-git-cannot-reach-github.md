---
title: Windows 上 git 连不上 GitHub，先别急着怪网络
date: 2026-09-28
tags: [Git, 网络排查, Windows, 代理]
summary: 浏览器能打开 GitHub，终端里 git clone 却卡住超时。代理明明开着，为什么 git 不走？因为它压根不读 Windows 的「系统代理」设置。
---

浏览器能正常打开 GitHub，代理软件也在跑，但终端里 `git clone` 就是卡住然后超时：

```
Failed to connect to github.com:443 after 21098 ms: Could not connect to server
```

或者：

```
fatal: unable to access 'https://github.com/...': CONNECT tunnel failed, response 502
```

这两个报错看起来都像网络问题，其实根因完全不同。先分清是哪一个，能省一半时间。

<!--more-->

## 先看报错里的秒数

`after 21098 ms` 里的**秒数是 TCP 层超时** —— 连接根本没建立起来。这**不是** DNS 失败，也**不是**认证失败。

看到这个数字，直接往代理方向查；看到 401 / publickey 那是另一类问题（凭据），别混。

而 `CONNECT tunnel failed, response 502` 说明**连接建立了，但代理把请求拒了**。这是代理本身的问题。

---

## 核心认知：「VPN 开着」≠「git 能走」

这是最容易误判的地方。两个独立原因叠加：

**① git for Windows 不读 Windows 的「系统代理」设置。**

它只认三样东西：

- `http.proxy` / `https.proxy` 配置项
- `HTTP_PROXY` / `HTTPS_PROXY` 环境变量
- TUN / 虚拟网卡模式（那种是接管全局流量）

所以 Clash 里那个「系统代理」开关，对 git **完全无效**。你在浏览器里验证「代理是通的」，对 git 没有任何参考价值。

**② 大多数代理客户端只在本机开一个端口，等应用自己来连。**

git 不主动去连 → 直连出国 → 被墙 → 超时。

---

## 步骤一：30 秒排除 DNS 和 hosts

```bash
nslookup github.com
grep -i github /c/Windows/System32/drivers/etc/hosts
```

DNS 能解析出真实 IP（如 `20.205.243.166`），hosts 里也没有被写死的条目 —— 那就不是 DNS 问题，往下走。

---

## 步骤二：⚠️ 先清掉被注入的代理变量

**这是最大的坑，我自己踩过。**

在各类 agent 沙箱、AI 编程助手的 Bash 会话里，`HTTP_PROXY` / `HTTPS_PROXY` 往往**已经被注入**成 `http://127.0.0.1:<随机端口>`（每次会话都不同）。这个代理去打 github 通常返回 502。

问题在于：如果你只 export 了小写 `https_proxy`，却**没清掉大写 `HTTPS_PROXY`**，git 仍然会去走那个坏代理 —— 然后你会得出一个错误结论：「用户的 Clash 也不通」。

正确做法是**先全清，再设**：

```bash
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
env | grep -iE "^(http|https|all)_proxy"     # 确认为空
```

我当时就是 `curl` 测代理返回 200、紧接着 git 报 502，来回折腾了几轮，最后发现是大写变量没清干净。

---

## 步骤三：找到代理在哪个端口

```bash
# 1) 有没有在跑的代理内核
tasklist | grep -iE "clash|verge|mihomo|v2ray|xray|sing-box|nekoray|shadowsocks"

# 2) 它监听哪个端口
netstat -ano | grep "LISTENING" | grep "127.0.0.1:"

# 3) 系统代理状态（仅作参考，git 不吃它）
netsh winhttp show proxy
```

几个经验值：

- **7890 是 Clash 系的 mixed 端口**，HTTP 和 SOCKS 都吃，优先用它
- **7891 是纯 SOCKS**，用 `http://` 去连会报 `Proxy CONNECT aborted` —— 别拿它当 HTTP 代理测，会误判
- Clash Party 的内核进程名是 `mihomo.exe`

---

## 步骤四：对比测试，锁定「是没走代理」还是「代理坏了」

```bash
# A. 直连（应该超时，复现问题）
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" --noproxy '*' \
  --connect-timeout 5 --max-time 8 https://github.com

# B. 走代理（应该是 200）
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" -x http://127.0.0.1:7890 \
  --connect-timeout 8 --max-time 15 https://github.com

# C. 决定性验证：git 自己走代理能不能拉到 refs
export HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890
export GIT_TERMINAL_PROMPT=0
timeout 45 git ls-remote --heads https://github.com/<owner>/<repo>.git
```

**A 超时 + B 返回 200 + C 打印出 `<sha> refs/heads/main`** → 根因确认：**git 没配代理**，网络和代理本身都没问题。

（C 那步偶尔会混进 `curl: (23) client returned ERROR on write` 之类的噪音，只要 `%{http_code}` 是 200 就算通过。）

---

## 步骤五：配代理 —— 推荐按域名配，别配全局

```bash
# 只让 github 走代理
git config --global http.https://github.com.proxy http://127.0.0.1:7890

# 验证
git ls-remote --heads https://github.com/hiyouga/LLaMA-Factory.git
```

**为什么按域名而不是全局？** 全局配置会连 gitee、公司内网仓库一起走代理，那些本来直连很快的反而变慢甚至失败。按域名最稳。

确实需要一刀切时：

```bash
git config --global http.proxy  http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

取消：

```bash
git config --global --unset http.https://github.com.proxy
git config --global --unset http.proxy
git config --global --unset https.proxy
```

端口变了（换客户端、改配置）就改成新端口。**想彻底免配只有一条路**：在 Clash 里开 TUN 模式接管全局流量 —— 那是唯一能让 git 不配置就走代理的方式。

---

## 步骤六：顺手体检三项

```bash
# 1. 镜像劫持 —— 有些机器被写死了 ghproxy 之类的镜像，导致所有 github 操作失败
git config --global --get-regexp insteadof

# 2. 残留代理 —— 上次配过没清干净
git config --global --get-regexp proxy

# 3. clone 落地位置
git clone https://github.com/<owner>/<repo>.git .
```

第 3 条解释一下：在 `D:\some dir` 下执行不带 `.` 的 clone，会生成 `D:\some dir\<repo>`。如果你想让内容**直接进当前空目录**，末尾要加那个点。

---

## 决策树

```
git 连不上 github
├─ nslookup 失败 / hosts 有写死条目
│     → DNS 问题
├─ 报 authentication / 401 / publickey
│     → 认证类问题（凭据管理器、token、SSH），不是网络
├─ 报 CONNECT tunnel failed 502
│     → 代理拒绝了请求，换端口或清掉污染的变量
└─ 报 Could not connect to server after N ms（TCP 超时）
      ├─ 代理客户端没运行        → 启动它
      ├─ 代理在跑但系统代理关着   → 正常现象，git 本来就不吃系统代理
      └─ 给 git 按域名配 proxy   → 解决
```

**一句话记住**：git 不读 Windows 的系统代理，得单独告诉它。

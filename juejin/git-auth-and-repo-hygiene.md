`git push` 报错的时候，第一反应通常是「凭据坏了」—— 然后去重新生成令牌、清配置、换 remote。

但有个更该先做的事：**确认到底推上去了没有。**

## 一、先看事实，别急着改配置

认证报错**不一定**代表没推成功 —— 可能只是某一次尝试失败，而之前的提交其实上去了。

```bash
git status -sb                              # 有没有 [ahead N]
git log --oneline origin/master..HEAD       # 本地领先远程几个提交
git ls-remote origin -h refs/heads/master   # 读远端真实指向（公开仓库匿名可读）
git reflog --all | head                     # 找 "update by push" 记录
```

如果 `git ls-remote` 显示的远端 commit 和你本地某个历史提交对得上，说明**之前已经推成功过**，只是后续提交没上去。

这种情况下继续折腾凭据是白费功夫 —— 问题在别处。

---

## 二、HTTPS 路径：令牌失效必须手动删凭据

### 重新生成令牌没用，这是个反直觉的点

GCM（Git Credential Manager）报这个的时候：

```
Incorrect credentials: 401 Unauthorized, Please remove invalid credentials manually
```

它是在明确告诉你：**它每次都从凭据管理器读旧凭据去试**。所以你去平台重新生成一个令牌，**不会自动生效** —— 旧的还躺在那儿。

必须手动删：

```bash
# 列出本机 git 相关凭据
cmdkey /list | tr -d '\000' | grep -a -i "gitee"

# 删除（注意 target 要带 LegacyGeneric:target= 前缀）
cmdkey /delete:LegacyGeneric:target=git:https://gitee.com
```

也可以走 GUI：控制面板 → 用户账户 → 凭据管理器 → Windows 凭据 → 删除 `git:https://<host>`。

> 那个 `tr -d '\000'` 不是装饰 —— `cmdkey` 的输出带 null 字节且是 GBK 编码，直接 `grep` 会被判定为二进制文件、什么都看不到。

### 重新认证的要点

- **Gitee / GitHub 早已不支持账号密码推代码，必须用 Personal Access Token**（Gitee 需要勾 `projects` 权限）
- 删掉旧凭据后，下次 `git push` 会重新弹窗
- 排查时用 `GIT_TERMINAL_PROMPT=0` 让它**快速失败而不是卡在交互提示上**：

```bash
GIT_TERMINAL_PROMPT=0 timeout 90 git push --progress 2>&1 | tail -15
```

---

## 三、切到 SSH（推荐，一次配好长期免密）

这是最省心的方案 —— 配好之后 HTTPS 那堆令牌问题**彻底绕开**。

```bash
# 1. 生成密钥（没有才生成；-N "" 表示不设密码短语）
ls ~/.ssh/id_ed25519.pub || ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -C "<你的邮箱>"
cat ~/.ssh/id_ed25519.pub      # 复制这一整行

# 2. 把公钥粘到平台的 SSH 公钥设置页（必须登录网页操作）

# 3. 验证 + 切换 remote + 推送
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -T git@gitee.com
git remote set-url origin git@gitee.com:<用户名>/<仓库>.git
git push
```

成功的样子：

```
Hi <用户名>! You've successfully authenticated, but GITEE.COM does not provide shell access.
```

**关键判断**：`ssh -T` 返回 `Permission denied (publickey)`，意思是**公钥还没加到平台**，不是本地配置有问题。别去折腾 ssh config。

排查时避免交互卡住：

```bash
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20"
```

---

## 四、`.git` 体积异常：误提交大文件之后

典型场景：某次 `git add -A` 把一个 torch wheel 加了进去，后来文件删了 —— 但**对象仍然以「不可达」状态占着磁盘**。

### 定位

```bash
du -sh .git
git count-objects -vH      # 看 size（散落对象总大小）与 size-pack
```

如果 `size` 有几 GB，但 `rev-list --objects --all` 里最大的对象只有几百 KB —— 说明垃圾全在**不可达对象**里。

```bash
# 找体积异常的散落对象
find .git/objects -type f -size +1048576c -printf '%s %p\n' | sort -rn | head

# 判断它是什么（看文件头魔数即可，不必读完）
git cat-file blob <sha> | head -c 120 | cat -v
```

常见魔数：`PK\x03\x04` = ZIP（wheel / 压缩包）、`\x89PNG` = PNG、`\x7fELF` = ELF。

### 回收

```bash
git fsck --no-progress     # 先确认哪些是 unreachable
git gc --prune=now         # 立即回收，无宽限期
```

核对：

```bash
git count-objects -vH      # count 应为 0
git fsck --no-progress     # 无输出 = 仓库健康
git log --oneline -5       # 历史完整
```

> ⚠️ `--prune=now` 会**立即**删除不可达对象，没有宽限期。执行前务必用 `find` / `cat-file` 确认那些确实是垃圾。历史提交里的对象不受影响。

---

## 五、`.gitignore` 的两个大坑

### 坑 1：已经 `git add` 过的文件，`.gitignore` 管不了

**这是最容易踩的一脚。** `.gitignore` **只对未跟踪的文件生效**。

如果有一次手滑 `git add .`，`.env`、`node_modules` 已经进了暂存区，你写多少条忽略规则都没用。

先判断现状：

```bash
git ls-files | grep -E "\.env$|node_modules/|__pycache__|\.idea/" | head
git log --oneline -1 2>&1 | head      # 有没有提交历史 → 决定用哪种修法
```

**情况 A：还没有任何 commit**（最干净）

```bash
git rm -r --cached .        # 只清索引，工作区文件一个都不动
git add .                   # 按新的 .gitignore 重新暂存
git ls-files | wc -l        # 对比前后数量（我实测过 785 → 37）
```

> `--cached` 是关键。**不传它就会真的删掉工作区文件。**

**情况 B：文件已经进过历史**

先清索引止血，再决定要不要清洗历史：

```bash
git rm -r --cached . && git add .
git commit -m "chore: 移除误提交的产物与密钥"
```

> ⚠️ **密钥一旦进过历史，就等于已经泄露。** 删文件不够 —— **必须去平台吊销并重新生成**
> （LLM API Key、云厂商 AK/SK、数据库密码都算）。

### 坑 2：靠肉眼看文件列表判断规则是否生效

正则很容易误判。比如 `grep -E "\.env"` 会把 `.env.example` 一起算进去，看起来像「还有 .env 没排除」，其实那是模板文件、本来就该提交。

让 git 自己告诉你哪条规则生效：

```bash
git check-ignore -v customer-service-backend/.env
# 输出：.gitignore:7:.env    customer-service-backend/.env
#        ↑ 哪个文件 : 第几行 : 具体规则
```

逐条核对必查项：

```bash
git ls-files | grep -E "\.env$"             # 期望【为空】
git ls-files | grep -E "\.env\.example$"    # 期望【保留】—— 模板要提交
git ls-files | wc -l                        # 数量应大幅下降
```

### `.gitignore` 该覆盖什么

| 类别 | 典型条目 |
|---|---|
| **密钥 / 环境变量（最高优先）** | `.env`、`.env.*`，并用 `!.env.example` 把模板救回来 |
| Python | `__pycache__/`、`*.py[cod]`、`.venv/`、`*.egg-info/`、`.pytest_cache/` |
| Node | `node_modules/`、`dist/`、`.vite/`、`*.local` |
| IDE | `.idea/`、`.vscode/`、`*.iml` |
| 系统 | `.DS_Store`、`Thumbs.db`、`desktop.ini` |
| 日志 / 临时 | `*.log`、`logs/`、`tmp/`、`*.bak` |

**⚠️ 反向提醒**：`uv.lock` / `package-lock.json` / `poetry.lock` 属于**必须提交**的。
它们的职责就是锁依赖版本，别顺手加进忽略列表 —— 这是很常见的误伤。

### 提交前做一次体积预演

```bash
git add -A --dry-run
git diff --cached --numstat | awk '{print $3}' | while read -r f; do
  [ -f "$f" ] && s=$(stat -c %s "$f") && [ "$s" -gt 1048576 ] && echo "⚠ $f ($((s/1024))KB)"
done
```

---

## 附：换行符警告是正常的

Windows 上 `git add` 出现这个不用管：

```
warning: LF will be replaced by CRLF
```

想统一，加个 `.gitattributes`：

```
* text=auto eol=lf
*.bat text eol=crlf
```

---

## 小结

| 现象 | 先做什么 |
|---|---|
| `Authentication failed` | 先 `git ls-remote` 确认远端指向，可能早就推成功了 |
| `Please remove invalid credentials manually` | 删凭据管理器里的旧条目，重新生成令牌没用 |
| `Permission denied (publickey)` | 公钥没加到平台，不是本地问题 |
| `.git` 几百 MB 但内容很少 | 误提交的大文件成了不可达对象，`gc --prune=now` |
| `.gitignore` 写了不生效 | 文件已被跟踪，`git rm -r --cached .` 重建索引 |
| 不确定哪条规则生效 | `git check-ignore -v <文件>` |

---

> 原文地址：https://jiaiyi.github.io/posts/git-auth-and-repo-hygiene.html
>
> 更多同类文章见我的博客：https://jiaiyi.github.io

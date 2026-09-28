这个博客从头到尾没用 Jekyll、Hexo、VitePress 任何框架 —— 一个 200 行的 Python 脚本把 Markdown 渲染成静态 HTML，推到 GitHub Pages。

不复杂，但过程中踩了四个坑，每个都值得记一下。

## 坑一：SSH 能认证，但建不了仓库

第一反应是配好 SSH 之后一切畅通。**其实不是。**

```
SSH key        → 只能操作【已存在】的仓库
API Token      → 才能创建新仓库
网页登录        → 才能创建新仓库
```

而且容易误判的一点：仓库不存在时，`git ls-remote` 报的是 **404**，不是 403。

```
$ git ls-remote git@gitee.com:user/repo.git
Auth error: 404 not found!
```

看到 404 别以为是权限问题去改配置 —— **先确认仓库到底存不存在**。

想全自动建仓库，用 token 调 API：

```python
urllib.request.Request(
    "https://api.github.com/user/repos",
    data=json.dumps({
        "name": "repo-name",
        "description": "...",
        "private": False,
        "auto_init": False,      # ★ 关键
    }).encode(),
    method="POST",
    headers={"Authorization": "token " + tok,
             "Accept": "application/vnd.github+json",
             "Content-Type": "application/json"},
)
```

**`auto_init: False` 这个别漏。** 如果让 GitHub 初始化（生成 README），远程会多一个 commit，你本地 push 时就得先合并 —— 对「我要推已有内容」的场景纯属添乱。

另外：经典 token 里，加 SSH 公钥需要 **`admin:public_key`** 权限，`repo` 不够。

**权限不足时 GitHub 返回的是 404 而不是 403**（故意隐藏资源是否存在）。我第一次差点以为是接口路径写错了，最后是靠读响应头 `X-OAuth-Scopes` 才定位到。

---

## 坑二：凭据会被偷偷留下来

我原本以为命令行指定一次性凭据就够了：

```bash
git -c credential.helper='!f() { echo username=xxx; echo "password=$TOK"; }; f' push
```

**但 push 成功之后，Windows 凭据管理器里还是多了一条：**

```
目标: LegacyGeneric:target=git:https://github.com
用户: xxx
```

原因：**git 在 push 成功后会调用整条 helper 链的 `store` 动作**。命令行 `-c` 的优先级虽然高，但**没法移除系统级的 `manager`** —— Git Credential Manager 是系统配置里的，它照存不误。

所以**只检查配置文件是查不出来的**。

推送后必须清理并验证：

```bash
cmdkey /delete:LegacyGeneric:target=git:https://github.com

# 核验（⚠️ cmdkey 输出是 GBK + 含 null 字节，直接 grep 会被判定成二进制）
cmdkey /list | tr -d '\000' | grep -a -i github
```

**完整核验清单**：

- [ ] 仓库 `.git/config` 的 remote url 不含 token
- [ ] `grep -rq "ghp_" .git/` 无残留
- [ ] 无 `~/.git-credentials`
- [ ] `git config --global --list` 无 token 项
- [ ] **`cmdkey /list` 无 `git:https://<host>` 条目** ← 最容易漏

最后别忘了去平台**撤销那个 token** —— 它已经离开你的机器了。

**长期方案还是 SSH**：配一次，之后推送不涉及任何凭据交换。

---

## 坑三：预构建的站点会被 Jekyll 搅乱

这个坑最隐蔽。我把构建产物放在 `docs/`，Pages 的 Source 设为 `main / docs`。

部署完打开站点：

- 首页 **HTTP 200** —— 看起来正常
- 但 `<title>` 是 `某某 | 某某`（这不是我写的标题格式）
- 首页渲染的是**仓库根目录的 README**，不是我的 `index.html`
- `/posts/*.html` 全部 **404**
- 只有 `/static/style.css` 是 200 —— 因为根目录恰好也有那个文件

**根因**：**GitHub Pages 默认对发布目录跑 Jekyll。** Jekyll 会忽略下划线开头的文件、把 README 当首页候选，并且不按原样处理你的预构建产物。

**解法：在发布目录放一个空的 `.nojekyll` 文件。**

```bash
touch docs/.nojekyll
```

（我把它写进了构建脚本，每次构建自动生成。）

### 这个坑真正的教训

**「返回 HTTP 200」不等于「发布成功」。**

首页确实返回 200，只是内容完全是错的。如果我只查状态码就宣布完成，这个 bug 会一直挂在那儿。

**该验什么**：

- `<title>` 的内容对不对
- 子路径资源的状态码（不只是首页）
- 页面里有没有不该出现的占位符残留

---

## 坑四：`docs/` 是预构建的，那网页上传文章就不生效

这个坑不是技术问题，是**架构问题**。

因为 Pages 发布的是**已经构建好的** `docs/`，而 `docs/` 是本地跑脚本生成的 —— 所以在 GitHub 网页上传一个 `posts/xxx.md`，**站点不会有任何反应**。

我一度以为这是「两个仓库不互通」，其实是我漏了一个环节。

**补上 GitHub Actions 就好。** `.github/workflows/build.yml`：

```yaml
name: Build blog

on:
  push:
    branches: [main]
    paths:
      - "posts/**"
      - "templates/**"
      - "static/**"
      - "build.py"
  workflow_dispatch:          # 也支持手动触发

permissions:
  contents: write             # ★ 要写权限才能把产物提交回仓库

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install markdown pygments

      - run: python build.py

      - name: 提交构建产物
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add docs
          if git diff --staged --quiet; then
            echo "docs/ 没有变化，跳过提交"
          else
            git commit -m "chore: rebuild docs [skip ci]"
            git push
          fi
```

**三个设计要点**：

1. **`permissions: contents: write`** —— 少了它，action 没法把产物推回来
2. **`paths` 过滤里不含 `docs/`** —— 否则「产物提交」会再次触发构建，无限循环
3. **commit message 带 `[skip ci]`** —— 双保险

另外：**推送 workflow 文件时，用 SSH 不需要额外权限**；如果用 HTTPS + token，GitHub 会要求 token 带 `workflow` scope（`repo` 不够）。

### 验证方式

改一篇文章推上去，然后**看远程是不是自己多了一个提交**：

```
你推送 5ad1dfb
  → 20 秒后远程出现 7d4cfae「chore: rebuild docs [skip ci]」   ← Actions 干的
  → 线上页面已包含新内容  ✓
```

我把这个当成了验收标准 —— **光看 workflow 文件在不在，不算数。**

---

## 现在的架构

```
blog/
├── posts/            文章源（Markdown）
├── templates/        模板
├── static/           样式
├── build.py          构建脚本（约 200 行）
├── docs/             构建产物 ← Pages 发布这个
│   └── .nojekyll     ★ 跳过 Jekyll
└── .github/workflows/build.yml
```

**为什么不用现成的框架？**

内容只有 Markdown 一种，读者只关心能不能打开、读起来舒不舒服。引入一套前端框架意味着依赖会过期、构建会变慢、某天要为升级折腾半天。

现在只有两个依赖（`markdown` + `pygments`），渲染逻辑在一个文件里，随时能自己改。

---

## 小结

| 坑 | 要点 |
|---|---|
| SSH 建不了仓库 | 建仓库要 token 或网页；`ls-remote` 报 404 说明仓库不存在 |
| 凭据被偷偷留下 | GCM 会调 `store`，只查配置发现不了 → 必须查 `cmdkey` |
| Jekyll 搅乱预构建站点 | 放 `.nojekyll`；**200 不等于发布成功** |
| 网页上传文章不生效 | 缺构建环节 → 加 Actions（含 `contents: write`） |

**最想强调的一条**：这个过程中我有两次差点「宣布完成」——
一次是只看 HTTP 200，一次是只看 workflow 文件存在。

**验收标准要定在结果上，不能定在「动作执行了」上。**

---

> 原文地址：https://jiaiyi.github.io/posts/github-pages-pitfalls.html
>
> 更多同类文章见我的博客：https://jiaiyi.github.io

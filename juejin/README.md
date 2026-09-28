# 掘金发布清单

共 14 篇。**摘要必须在 50~100 字之间**，否则创建草稿会失败。

## 发布方式

**手动（推荐先用这个试水）**
1. 打开 https://juejin.cn/editor/drafts/new
2. 标题、分类、标签按下表填，摘要粘进「摘要」输入框
3. `juejin/<slug>.md` 内容整体粘贴进正文区（编辑器支持 Markdown）
4. 发布

**自动（走掘金开放接口）**
```
POST https://api.juejin.cn/content_api/v1/article_draft/create
POST https://api.juejin.cn/content_api/v1/article/publish
鉴权：Cookie（sessionid + passport_csrf_token）
```

---

## 1. Milvus 报 code=1100？两类 schema 里看不出来的约束

- **标题**：`Milvus 报 code=1100？两类 schema 里看不出来的约束`
- **分类**：后端
- **标签**：Milvus、向量数据库、Python
- **摘要**（94 字）：往 Milvus 插数据报 more fieldData has pass in / varchar field got nil，对着 schema 检查却找不出问题 —— 这两条约束不在定义里，只有真插一次才会炸出来。
- **正文文件**：`juejin/milvus-code-1100.md`
- **原文链接**：https://jiaiyi.github.io/posts/milvus-code-1100.html

## 2. 装完 PyTorch 发现 GPU 用不上？先看看你装的是不是 CPU 版

- **标题**：`装完 PyTorch 发现 GPU 用不上？先看看你装的是不是 CPU 版`
- **分类**：人工智能
- **标签**：PyTorch、Windows、环境配置、深度学习
- **摘要**（99 字）：pip install torch 一路顺利，torch.cuda.is_available() 却是 False。根因很可能是：PyPI（含国内镜像）上的 Windows torch wheel 根本就是 CPU 版。
- **正文文件**：`juejin/pytorch-cpu-wheel.md`
- **原文链接**：https://jiaiyi.github.io/posts/pytorch-cpu-wheel.html

## 3. docx 转 Markdown：标题层级不在样式名里，代码块也不在

- **标题**：`docx 转 Markdown：标题层级不在样式名里，代码块也不在`
- **分类**：后端
- **标签**：Python、OOXML、文档处理
- **摘要**（90 字）：用 Python 解析 .docx 时，最容易踩的不是解析本身，而是文档里根本没按你想的方式存信息 —— 标题层级藏在 outlineLvl 里，代码块只靠字体区分，而错误会一路传到下游才爆出来。
- **正文文件**：`juejin/docx-ooxml-pitfalls.md`
- **原文链接**：https://jiaiyi.github.io/posts/docx-ooxml-pitfalls.html

## 4. Windows 说「文件夹正在使用」，却不告诉你是谁

- **标题**：`Windows 说「文件夹正在使用」，却不告诉你是谁`
- **分类**：开发工具
- **标签**：Windows、排查、工具链
- **摘要**（86 字）：想重命名或删除一个文件夹，Explorer 只回一句「操作无法完成，因为其中的文件夹或文件已在另一程序中打开」—— 但不说哪个程序。而真正的占用者，往往是你正开着的那台编辑器。
- **正文文件**：`juejin/windows-locked-folder.md`
- **原文链接**：https://jiaiyi.github.io/posts/windows-locked-folder.html

## 5. WSL 里 curl 一片空白，Windows 却好得很

- **标题**：`WSL 里 curl 一片空白，Windows 却好得很`
- **分类**：开发工具
- **标签**：WSL、代理、Windows、Linux
- **摘要**（80 字）：Windows 里 curl 畅通无阻，WSL 里 curl 连一行响应头都不打印，pip 卡在第一个包上不动。根因是代理只绑在回环地址上，而 WSL 住在另一个网络命名空间里。
- **正文文件**：`juejin/wsl-proxy.md`
- **原文链接**：https://jiaiyi.github.io/posts/wsl-proxy.html

## 6. 打包好的 Electron 应用「启动即崩」？先查环境变量

- **标题**：`打包好的 Electron 应用「启动即崩」？先查环境变量`
- **分类**：前端
- **标签**：Electron、Windows、调试
- **摘要**（78 字）：进程秒退、exit code 0、日志文件根本不存在 —— 看起来像构建坏了或者 exe 被截断。但如果它是在 AI 编程助手的 shell 里启动的，八成是环境变量被污染了。
- **正文文件**：`juejin/electron-launch-verify.md`
- **原文链接**：https://jiaiyi.github.io/posts/electron-launch-verify.html

## 7. 验证前端不一定要装浏览器自动化框架

- **标题**：`验证前端不一定要装浏览器自动化框架`
- **分类**：前端
- **标签**：前端、测试、Chrome、调试
- **摘要**（83 字）：想在受限网络里验证一个 JS 渲染的页面，最容易卡在「下载 Chromium」这一步。其实系统上早就有 Chrome 了 —— 而且有两招根本不需要启动浏览器，就能覆盖大部分问题。
- **正文文件**：`juejin/frontend-verification-without-framework.md`
- **原文链接**：https://jiaiyi.github.io/posts/frontend-verification-without-framework.html

## 8. git push 报认证失败，但代码可能早就推上去了

- **标题**：`git push 报认证失败，但代码可能早就推上去了`
- **分类**：开发工具
- **标签**：Git、凭据管理、仓库卫生
- **摘要**（75 字）：看到 Authentication failed 就急着换令牌、改配置，是常见的第一步错。先花 10 秒确认远端到底指向哪个 commit，能省掉一大圈无效折腾。
- **正文文件**：`juejin/git-auth-and-repo-hygiene.md`
- **原文链接**：https://jiaiyi.github.io/posts/git-auth-and-repo-hygiene.html

## 9. Windows 上 git 连不上 GitHub，先别急着怪网络

- **标题**：`Windows 上 git 连不上 GitHub，先别急着怪网络`
- **分类**：开发工具
- **标签**：Git、网络排查、Windows、代理
- **摘要**（70 字）：浏览器能打开 GitHub，终端里 git clone 却卡住超时。代理明明开着，为什么 git 不走？因为它压根不读 Windows 的「系统代理」设置。
- **正文文件**：`juejin/git-cannot-reach-github.md`
- **原文链接**：https://jiaiyi.github.io/posts/git-cannot-reach-github.html

## 10. 用 GitHub Pages 搭博客，我踩的四个坑

- **标题**：`用 GitHub Pages 搭博客，我踩的四个坑`
- **分类**：开发工具
- **标签**：GitHub、Pages、CI、静态站点
- **摘要**（80 字）：从建仓库到自动发布，全程没用任何框架。踩到四件事：SSH 建不了仓库、凭据会被偷偷存下来、预构建的站点会被 Jekyll 搅乱、以及「返回 200」不等于「发布成功」。
- **正文文件**：`juejin/github-pages-pitfalls.md`
- **原文链接**：https://jiaiyi.github.io/posts/github-pages-pitfalls.html

## 11. Hermes 的五套「插件」根本不是一回事

- **标题**：`Hermes 的五套「插件」根本不是一回事`
- **分类**：开发工具
- **标签**：Hermes、插件系统、工具链
- **摘要**（60 字）：装上插件却不生效、改了配置没反应 —— 大多数时候是因为把五套互不相干的扩展机制混为一谈了。先分清是哪一类，再看对应的开关。
- **正文文件**：`juejin/hermes-plugin-ecosystem.md`
- **原文链接**：https://jiaiyi.github.io/posts/hermes-plugin-ecosystem.html

## 12. PyCharm 里解释器加不进去？问题可能不在解释器

- **标题**：`PyCharm 里解释器加不进去？问题可能不在解释器`
- **分类**：开发工具
- **标签**：PyCharm、uv、Python、环境配置
- **摘要**（72 字）：在 PyCharm 里给 uv 项目配解释器，选了路径却报「不是有效 Python」，或者加完面板里依然不显示。查了半天解释器，其实根因在 .iml 文件上。
- **正文文件**：`juejin/pycharm-uv-interpreter.md`
- **原文链接**：https://jiaiyi.github.io/posts/pycharm-uv-interpreter.html

## 13. RAG 切片调优：先诊断，别先调参

- **标题**：`RAG 切片调优：先诊断，别先调参`
- **分类**：人工智能
- **标签**：RAG、检索、中文处理、向量数据库
- **摘要**（70 字）：检索回来的是半句话、或者召回一堆只有一个标题的空片段 —— 这种问题调 chunk_size 之前，得先量出来它到底有多碎。凭感觉调参只会来回打转。
- **正文文件**：`juejin/rag-chunking-tuning.md`
- **原文链接**：https://jiaiyi.github.io/posts/rag-chunking-tuning.html

## 14. RAG 检索路由：为什么「精确问课程名」反而答错

- **标题**：`RAG 检索路由：为什么「精确问课程名」反而答错`
- **分类**：人工智能
- **标签**：RAG、检索、路由、LLM
- **摘要**（72 字）：一个反直觉的实测结果：用户已经说出对象名字了，向量检索给出的却是另一门课，而且相似度分数高达 0.79。光看分数救不了 —— 这类问题必须靠路由解决。
- **正文文件**：`juejin/rag-retrieval-routing.md`
- **原文链接**：https://jiaiyi.github.io/posts/rag-retrieval-routing.html

# CSDN 发布清单

共 5 篇。源文件在本目录，按下面的元信息粘贴即可。

## 发布步骤

1. 打开 https://blog.csdn.net/qq_mp/write （或点「写文章」）
2. 标题、标签、分类按下表填
3. `csdn/<slug>.md` 的内容**整体复制**粘贴进正文区（编辑器支持 Markdown）
4. 确认预览无误后点「发布文章」

> 文中若含代码块，粘贴后检查一下缩进是否保留；CSDN 的 Markdown 模式偶尔会吞掉围栏。

---

## 1. Milvus 报 code=1100？两类 schema 里看不出来的约束

- **标题**：`Milvus 报 code=1100？两类 schema 里看不出来的约束`
- **标签**：Milvus、向量数据库、Python、RAG
- **分类专栏**：向量数据库
- **正文文件**：`csdn/milvus-code-1100.md`（2966 字符）
- **原文链接**：https://jiaiyi.github.io/posts/milvus-code-1100.html

摘要：往 Milvus 插数据报 more fieldData has pass in / varchar field got nil，对着 schema 反复检查却找不出问题。这两条约束不在 schema 定义里，只有真插一次才会炸出来。

## 2. 装完 PyTorch 发现 GPU 用不上？先看看你装的是不是 CPU 版

- **标题**：`装完 PyTorch 发现 GPU 用不上？先看看你装的是不是 CPU 版`
- **标签**：PyTorch、Windows、环境配置、深度学习
- **分类专栏**：深度学习环境
- **正文文件**：`csdn/pytorch-cpu-wheel.md`（3122 字符）
- **原文链接**：https://jiaiyi.github.io/posts/pytorch-cpu-wheel.html

摘要：pip install torch 一路顺利，torch.cuda.is_available() 却是 False。根因很可能是：PyPI（含国内镜像）上的 Windows torch wheel 根本就是 CPU 版。

## 3. docx 转 Markdown：标题层级不在样式名里，代码块也不在

- **标题**：`docx 转 Markdown：标题层级不在样式名里，代码块也不在`
- **标签**：Python、OOXML、文档处理
- **分类专栏**：Python 实战
- **正文文件**：`csdn/docx-ooxml-pitfalls.md`（4207 字符）
- **原文链接**：https://jiaiyi.github.io/posts/docx-ooxml-pitfalls.html

摘要：用 Python 解析 .docx 时，最容易踩的不是解析本身，而是文档里根本没按你想的方式存信息 —— 标题层级藏在 outlineLvl 里，代码块只靠字体区分，而错误会一路传到下游才爆出来。

## 4. Windows 说「文件夹正在使用」，却不告诉你是谁

- **标题**：`Windows 说「文件夹正在使用」，却不告诉你是谁`
- **标签**：Windows、排查、工具链、文件管理、经验分享
- **分类专栏**：Windows 踩坑
- **正文文件**：`csdn/windows-locked-folder.md`（3681 字符）
- **原文链接**：https://jiaiyi.github.io/posts/windows-locked-folder.html

摘要：想重命名或删除一个文件夹，Explorer 只回一句「操作无法完成，因为其中的文件夹或文件已在另一程序中打开」—— 但不说哪个程序。而真正的占用者，往往是你正开着的那台编辑器。

## 5. WSL 里 curl 一片空白，Windows 却好得很

- **标题**：`WSL 里 curl 一片空白，Windows 却好得很`
- **标签**：WSL、代理、Windows、Linux、环境配置
- **分类专栏**：开发环境
- **正文文件**：`csdn/wsl-proxy.md`（3426 字符）
- **原文链接**：https://jiaiyi.github.io/posts/wsl-proxy.html

摘要：Windows 里 curl 畅通无阻，WSL 里 curl 连一行响应头都不打印，pip 卡在第一个包上不动。根因是代理只绑在回环地址上，而 WSL 住在另一个网络命名空间里。

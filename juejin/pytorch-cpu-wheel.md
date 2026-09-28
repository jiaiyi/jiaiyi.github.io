在 Windows 上装 PyTorch，最容易踩的坑不是装不上，而是**装上了却用不了 GPU** ——
安装全程无报错，`import torch` 也正常，直到你写训练代码，`torch.cuda.is_available()`
返回 `False` 才发现不对。

显卡明明在，驱动也没问题。

检查一下版本号，你会看到关键线索：

```python
>>> import torch
>>> torch.__version__
'2.11.0+cpu'          # ← 这个 +cpu 就是问题所在
>>> torch.cuda.is_available()
False
```
## 根因：PyPI 上的 Windows torch wheel 是 CPU 版

这一点很多人不知道：**PyPI（包括清华、阿里等国内镜像）上提供的 Windows `torch`
wheel 只有约 190 MB —— 那个体积就是 CPU 版。**

GPU 版不在 PyPI 上，只在 PyTorch 官方源 `download.pytorch.org`，体积 **2.5 GB 以上**。

于是就有了这个局面：

```bash
pip install torch torchvision torchaudio          # 一切正常
python -c "import torch; print(torch.__version__)"
# 2.11.0+cpu        ← 关键就是这个 +cpu
```

官方 README 里那句轻描淡写的「Windows 平台需要额外手动安装 GPU 版本的 PyTorch
依赖包」，说的就是这件事。

---

## 不下载就能判断 wheel 是哪种

下载 2.5 GB 才发现装错，代价太大。可以直接查 PyPI 的 JSON 接口看体积，秒出结果：

```python
import json, urllib.request

d = json.load(urllib.request.urlopen(
    "https://pypi.tuna.tsinghua.edu.cn/pypi/torch/json"))

for v, files in d["releases"].items():
    for f in files:
        if "win_amd64" in f["filename"]:
            mb = f["size"] / 1024 / 1024
            print(v, f["filename"], "%.0f MB" % mb,
                  "CUDA版" if mb > 800 else "CPU版")
```

输出里会看到 Windows 轮子清一色是 190 MB 上下 —— 全是 CPU 版。

> 顺带一个坑：清华大学镜像支持 `/pypi/<pkg>/json`，但**不支持**
> `/pypi/<pkg>/<version>/json`（单版本那个路径会 404）。别在那儿浪费时间。

---

## 版本必须严格配套

装 GPU 版时，`torch` / `torchvision` / `torchaudio` 三者的版本要严格对应，否则会
**静默降级成 CPU 算子** —— 不报错，但跑起来是 CPU 速度。

| torch | torchvision | torchaudio |
|---|---|---|
| 2.11.x | 0.26.0 | 2.11.0 |

**验证方式不是看 install 是否成功，而是看版本字符串有没有 `+cuXXX` 后缀：**

```python
import torch, torchvision, torchaudio
print(torch.__version__, torchvision.__version__, torchaudio.__version__)

# 正确: 2.11.0+cu128  0.26.0+cu128  2.11.0+cu128
# 错误: 2.11.0+cu128  0.26.0+cpu   2.11.0+cpu     ← 混进了 CPU 版
```

第二种情况特别隐蔽：`torch` 装对了，但 `torchvision` 是 CPU 版。这种情况下
`cuda.is_available()` 可能还是 `True`，但实际跑到卷积就出问题。

---

## 正确的安装命令

要装 GPU 版，必须**显式指定 PyTorch 官方源**，而不是让它去 PyPI 或国内镜像找：

```bash
uv pip install "torchvision==0.26.0+cu128" "torchaudio==2.11.0+cu128" \
  --index-url https://download.pytorch.org/whl/cu128 --no-deps
```

几个要点：

- **`--index-url` 而不是 `--extra-index-url`**：用后者时，如果同时配了清华镜像，
  uv 可能优先拿到 CPU 轮子。把它设成唯一的 index 才稳。
- **`--no-deps`**：避免它顺带重解析整个依赖树，把别的包也搅动一遍。
- 国内下载 2.5 GB 会很慢，建议挂代理。

查某个源上到底有哪些可用版本（`curl` 可能因为代理环境变量而失败，用 Python 抓更稳）：

```python
import urllib.request, re

html = urllib.request.urlopen(urllib.request.Request(
    "https://download.pytorch.org/whl/cu128/torchvision/",
    headers={"User-Agent": "uv/0.12.7"})).read().decode()

print(sorted(set(re.findall(
    r"torchvision-([\d.]+)%2Bcu128-cp311-cp311-win_amd64\.whl", html))))
```

注意 URL 里的 `%2B` 就是 `+` 的转义，正则里别写错。

---

## 小结

| 检查项 | 正确 | 错误信号 |
|---|---|---|
| wheel 体积 | 2.5 GB+ | 190 MB |
| 版本字符串 | `2.11.0+cu128` | `2.11.0+cpu` |
| 三个包是否一致 | 全是 `+cuXXX` | 混着 `+cpu` |
| `cuda.is_available()` | `True` | `False` |

最省事的排查顺序：**先看 `torch.__version__` 有没有 `+cpu`** ——
有的话不用继续查了，直接去装官方源的 GPU 版。

---

> 原文地址：https://jiaiyi.github.io/posts/pytorch-cpu-wheel.html
>
> 更多同类文章见我的博客：https://jiaiyi.github.io

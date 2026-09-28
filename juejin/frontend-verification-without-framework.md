要验证一个前端页面到底渲染成什么样，第一反应通常是装 Playwright / Puppeteer。

但它们都要下载一个 Chromium（约 196MB）。在企业网络或受限环境里，这一步经常失败 —— 我实测过：工具本体装得上，但 Chromium 从 Google 的存储服务下载**三次重试全部超时**。

**别卡在这里反复重试。** 系统上通常已经装了 Chrome 或 Edge，直接用就够。

下面四招按「由轻到重」排列。**前两招完全不启动浏览器**，却能覆盖大部分实际问题。

## 一、HTTP 连通性批量扫（最轻）

```bash
for p in "/" "/a.html" "/b.html" "/api/x" "/health"; do
  out=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:9000$p")
  printf "  %-24s → %s\n" "$p" "$out"
done
```

两个坑：

⚠️ **`-w "%{size_download}"` 有时会打印 0** —— 别据此判断响应体为空。要看内容就单独 `| wc -c`。

⚠️ **中文查询参数必须 URL 编码**，否则 curl 发出的请求会失败，看起来像接口有 bug：

```bash
curl -s -G "http://127.0.0.1:9000/courses" \
  --data-urlencode "category=数学" --data-urlencode "limit=20"
```

---

## 二、前后端字段契约核对（最有价值的一招）

**前端最常见的 bug 不是「接口挂了」，而是字段对不上** —— 页面读 `a.b`，接口返回的是 `a.c`。

把「页面 JS 里读取的字段集合」和「接口实际返回的键集合」做差集，一次就能全暴露：

```python
# 从页面 JS 里人工列出它读取的字段
need = {'course_code', 'course_name', 'module_count', 'total_hours'}

d = get("/courses?limit=1")['items'][0]
print(need - set(d))
# 空集 = 契约一致
# 非空 = 这些字段页面会读到 undefined
```

这一招的价值在于：**它把「页面某个位置显示空白」这种模糊现象，变成了一份精确的字段清单**。不用逐个点开页面找哪里没渲染出来。

### 配套纪律一：`total` 必须是「匹配总数」

写成 `len(items)` 会让页面把**一页的条数**当成总数。

我踩过这个：课程页显示「共 50 门」，实际有 219 门 —— 因为接口返回的 `total` 其实是那一页的数量。

分页接口应该统一返回：

```json
{ "total": 219, "limit": 50, "offset": 0, "items": [...] }
```

### 配套纪律二：统计口径与过滤口径必须同源

分类 chip 上的计数，和点进去之后的列表总数对不上 —— 几乎总是因为两处用了不同的过滤条件。

实测过一个例子：chip 按 `category` 字段聚合得到 45，列表用 `category_path` 正则匹配得到 51。差额来自那条正则把「考试与升学 / 中学数学」这种**带父级路径**的也算了进来。

**修法：把两处收敛到同一个查询构造函数。** 不是去调正则，是让它们共用一份逻辑。

---

## 三、系统 Chrome headless 截图（能拍到 JS 渲染后的真实内容）

```bash
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"   # Windows
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-sandbox \
  --window-size=1400,1000 --virtual-time-budget=9000 \
  --screenshot="D:\\path\\out.png" "http://127.0.0.1:9000/page.html"
```

几个关键点：

- **`--virtual-time-budget=9000`** —— 给页面 9 秒**虚拟时间**，让它把 `fetch` 的数据拿回来、JS 渲染完再截图。**没有这个参数，动态页面只能拍到空壳。** 这是最容易被忽略的一个。
- **截图路径要用宿主 OS 的风格**。Chrome 是 Windows 程序，你写 `/tmp/x.png` 会落到意料之外的位置。
- `--window-size=W,H` 的高度要写够，否则长列表会被裁掉。
- 拍完**用 Read 工具直接看 PNG 核对** —— 比读 HTML 可靠得多（HTML 里有内容不代表渲染出来了）。

### 一个设计上的建议：深链接让页面更容易验证

把「展开详情」这类交互用 **URL hash** 承载（如 `#course=xxx`），就能直接截到详情态，不需要模拟点击。

而且这**同时是个真功能** —— 链接可分享、浏览器前进后退可用。为了可测性做的设计，顺手把产品体验也改好了。

---

## 四、把页面的 JS 函数抽出来单测

有些渲染逻辑只有交互之后才触发（比如「点击展开后才渲染的区块」），截图覆盖不到。

可以从页面源码里**按括号配对截取函数源码**，`eval` 之后喂用例：

```js
function pick(src, name) {
  const i = src.indexOf('function ' + name + '(');
  let depth = 0, started = false;
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') { depth++; started = true; }
    else if (src[j] === '}') { depth--; if (started && depth === 0) return src.slice(i, j + 1); }
  }
}

eval(pick(html, 'myRenderFn'));
// 然后喂正常用例 + 边界用例（没有输入 / 空结果 / 另一种写法）
```

**为什么必须从源码抽**：另写一份「等价实现」等于测了个假的 —— 页面改了你的测试不知道，还全绿。**抽源码测的才是页面真正在跑的那份逻辑。**

⚠️ 写这类测试时，**把用例里的模板字符串放到 `.js` 文件里跑**，不要塞进 bash heredoc ——
`${...}` 会被 shell 抢先解释，报 `Bad substitution`。

---

## 五、收尾清单

- **前后端地址统一用同源相对路径**（`location.origin`），别硬编码 `http://127.0.0.1:8000` ——
  换部署环境就失效，还自带跨域问题
- **多服务合并成单端口时，不要重写已有路由定义**（会丢掉各服务独立启动的能力）。
  把子应用路由合并进主应用、跳过框架级路由（`/docs`、`/openapi.json`、`/redoc`）就行
- **改完接口/页面记得重启服务再验证** —— 热重载往往不覆盖新加的文件

---

## 小结

| 招数 | 成本 | 能解决什么 |
|---|---|---|
| HTTP 连通性扫 | 最低 | 路径/接口是否活着 |
| **字段契约核对** | 低 | **页面读到 undefined 的字段（最高频 bug）** |
| headless 截图 | 中 | JS 渲染后的真实观感 |
| 抽源码单测 | 中高 | 交互后才触发的逻辑 |

**核心认知**：验证前端最重的依赖是「下载一个浏览器」，而那个依赖**往往是不必要的** ——
系统里已有的 Chrome 完全能胜任。

按「由轻到重」的顺序试，大部分问题在前两步就能定位，根本轮不到启动浏览器。

---

> 原文地址：https://jiaiyi.github.io/posts/frontend-verification-without-framework.html
>
> 更多同类文章见我的博客：https://jiaiyi.github.io

先说现象：一个把四个 Web 页面合并到同一端口上的 FastAPI 服务，「历史记录」列表能正常读出来，点「清空对话」却失败 —— 浏览器里只弹一句通用提示，**服务端没有 500，日志干干净净**。

这种「前端说失败、后端说没事」的 bug，比抛异常难查十倍。

## 一、先定位到「请求根本没进来」

排查顺序很关键。先别改代码，先确认一件事：**那个请求到底有没有到达处理函数。**

在路由函数第一行加一行日志：

```python
@router.delete("/history/{session_id}")
async def clear_history(session_id: str):
    logger.info("clear_history hit: %s", session_id)
    ...
```

结果这行日志**一次都没打印**。但同一个路径的 GET 是正常的：

```python
@router.get("/history/{session_id}")   # 这个正常
async def get_history(session_id: str): ...
```

也就是说：**路径存在，处理函数存在，但 DELETE 这个方法在路由表里不存在。**

浏览器看到的是一个标准的 **405 Method Not Allowed** —— 而前端只 catch 了 `res.ok === false`，统一弹了一句「操作失败」，把状态码吞掉了。这就是「服务端看起来没事」的原因。

## 二、根因：合并路由时，去重键只用了一半

这个服务为了「单端口多页面」，把多个子应用的路由手动合并进主应用，代码大致是这样：

```python
seen = {route.path for route in target.routes}
for sub_app in sub_apps:
    for route in sub_app.routes:
        if route.path in seen:      # ← 问题在这一行
            continue
        seen.add(route.path)
        target.routes.append(route)
```

**去重键只有 `path`。** 于是当 `/history/{session_id}` 上的 `GET` 先被注册进 `seen`，后面同路径的 `DELETE` 就被当成「重复」整条跳过了。

一行 `continue`，一个 HTTP 方法凭空消失。

## 三、修法

去重键改成「路径 + 方法集合」：

```python
def _route_key(route):
    path = getattr(route, "path", None)
    methods = getattr(route, "methods", None) or ()
    return (path, tuple(sorted(methods)))
```

`methods` 在 Starlette 里是 `set`，必须 `sorted` 之后才能当键 —— 集合本身不可哈希，而且顺序不固定，直接用会让两次运行的行为不一致。

合并时同时在启动日志里把结果打出来：

```python
merged.append(f"{'+'.join(sorted(route.methods)) or 'MOUNT'} {path}")
```

修完之后启动日志里能看到同一路径的两行：

```
GET /history/{session_id}
DELETE /history/{session_id}
```

**这条日志本身就是最好的回归测试** —— 下次谁再动合并逻辑，少一个方法一眼就能看出来。

## 四、四条经验

**① 去重键是「资源 + 动作」，不是资源。** 只要你的框架允许同一路径挂多个方法（FastAPI、Express、Flask 的 `methods=[...]` 都是），去重键就必须带上方法。

**② 手动合并路由属于「框架没管的那部分」。** `include_router` 帮你做合并时不会有这个问题；一旦自己写 `target.routes.append()`，就等于接手了框架的内部约束 —— 而这类约束**不会报错，只会静默丢东西**。

**③ 405 一定要在看板上能看见。** 前端把 `status` 吞成一句「操作失败」，等于把最有价值的线索扔了。至少打一条 `console.warn(status, url, method)`。

**④ 一个路径挂多个方法时，补一条冒烟测试。** 不用测业务逻辑，只测「路由表里有没有这个方法」：

```python
def test_history_has_both_methods():
    app = create_app()
    paths = {(r.path, m) for r in app.routes for m in (getattr(r, "methods", None) or ())}
    assert ("/history/{session_id}", "GET") in paths
    assert ("/history/{session_id}", "DELETE") in paths
```

---

## 小结

| 现象 | 容易误判成 | 实际原因 |
|---|---|---|
| 前端弹「操作失败」 | 后端抛异常 | 405，请求没到处理函数 |
| 日志里没有 500 | 服务是好的 | 路由层面就被拦掉了 |
| 同路径 GET 正常 | 路由注册没问题 | 只有那一个方法被去重丢弃 |

这类 bug 的共同点是**静默**：没有异常栈、没有错误日志，只有一个功能悄悄不工作。所以真正值得记的不是这一行的改法，而是那条纪律 —— **凡是自己接管框架行为的地方，都要有一段能看见结果的日志或断言。**

---

> 原文地址：https://jiaiyi.github.io/posts/fastapi-route-merge-methods.html
>
> 更多同类文章见我的博客：https://jiaiyi.github.io

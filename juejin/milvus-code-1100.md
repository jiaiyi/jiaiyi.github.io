往 Milvus 插数据时遇到 `MilvusException (code=1100)`，第一反应通常是去翻 schema
核对字段。但下面这两条约束**在 schema 定义里根本看不出来** —— 声明得完全合法，
insert 的时候才报错。

我在这上面来回折腾过，这里一次说清。

## 现象

两条报错长这样：

```
MilvusException (code=1100, message=more fieldData has pass in:
                 invalid parameter[expected=18][actual=19])

MilvusException (code=1100, message=varchar field 'xxx' is illegal,
                 array type mismatch: invalid parameter[expected=need string array][actual=got nil])
```

第一条看着像「字段传多了」，第二条像「类型不对」。但如果你盯着 schema 看，
会发现字段数量对得上、类型也对。

问题出在别处。

---

## 坑一：`auto_id=True` 的主键不能再显式传值

建集合时如果主键声明了 `auto_id=True`，那么 insert 时**这个字段必须整个不传**。

我最初的想法是「反正会自动生成，那我传 `None` 占个位总行吧」——

```python
# 不行
rows = [{"chunk_id": None, "content": "...", "embedding": [...]}]
```

```python
# 也不行
rows = [{"chunk_id": 0, "content": "...", "embedding": [...]}]
```

两种都会报 `more fieldData has pass in`。

**怎么读这个报错**：

```
expected=18   ← 声明字段数 + 1
actual=19     ← 实际传的字段数
```

那个 `+1` 容易让人困惑：如果你开了 `enable_dynamic_field=True`，Milvus 内部会多一个
`$meta` 字段，所以 `expected` 比你数出来的字段数多一个。

而 `actual` 比 `expected` 多出来的那一个，就是你显式传的主键。

**结论：`None` 和 `0` 都不算「不传」。** Python 的 dict 里只要这个 key 存在，
就会被算进字段数。必须 `pop` 掉。

---

## 坑二：VARCHAR 字段不接受 `None`

这条更隐蔽，因为它**适用于所有标量字段**，不只是你重点关注的那几个。

```python
# 报错：varchar field 'xxx' is illegal,
#       array type mismatch: invalid parameter[expected=need string array][actual=got nil]
```

只要某个 VARCHAR 字段的值是 `None`，整行就插不进去。

真实场景里很容易踩：你有个可选字段（比如 `parent_title`、`summary`、`source_url`），
大部分数据有值，某一条恰好没有 —— 于是 `None` 混进了批次，整批 insert 失败。

`None` 必须转成空字符串 `""`。

---

## 统一清洗写法

关键点是**把它放在唯一的写入点** —— 所有插入都经过的那个函数。
散落各处做清洗，早晚会漏掉一条路径。

```python
def clean_rows_for_milvus(chunks):
    rows = []
    for chunk in chunks:
        row = dict(chunk)              # ★ 必须复制，见下一节
        row.pop("chunk_id", None)      # auto_id 主键不能显式传
        for k, v in row.items():
            if v is None:
                row[k] = ""            # VARCHAR 不吃 None
        rows.append(row)
    return rows
```

插入之后，用返回的 ids 把主键回填到原始对象上 —— 后续还要用这个 id 做关联：

```python
insert_result = client.insert(collection_name=NAME, data=rows)
ids = insert_result["ids"]
for i, chunk in enumerate(chunks):
    chunk["chunk_id"] = ids[i]
```

---

## 一个容易写错的地方：`dict(chunk)` 不能省

上面那行 `row = dict(chunk)` 看着像是多余的防御性代码，其实是必须的。

如果偷懒写成：

```python
row = chunk                      # ✗
row.pop("chunk_id", None)        # 这一行把原始对象的主键也删了
```

那么 `pop` 作用在**同一个对象**上，原始 chunk 的 `chunk_id` 被删掉了。
末尾那句回填 `chunk["chunk_id"] = ids[i]` 虽然会执行，但你之前已经
把 chunk 里原有的值抹掉了 —— 如果这段代码在重试路径上被调用第二次，
行为和第一次就不一样了。

**这是个不报错但结果错的 bug**，比直接抛异常麻烦得多。

一行 `dict()` 就能避免。

---

## 小结

| 约束 | 触发条件 | 处理 |
|---|---|---|
| `auto_id` 主键不可显式传 | 字段以 `None` 或 `0` 存在 | `row.pop("chunk_id", None)` |
| VARCHAR 不接受 `None` | 任一标量字段为 `None` | `None` → `""` |

两条都属于「不在 schema 里，插一次才知道」的类型。如果你正在写 Milvus 的写入层，
建议一开始就把清洗函数收敛到单个入口，别等到踩了再回头重构。

---

> 原文地址：https://jiaiyi.github.io/posts/milvus-code-1100.html
>
> 更多同类文章见我的博客：https://jiaiyi.github.io

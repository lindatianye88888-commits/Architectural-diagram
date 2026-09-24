# 三源核验记录

`chengdudong_observations.geojson` 保存百度地图、Google Earth、现场或正式资料发现的差异。它不是第二份 OSM，也不应包含从专有地图批量复制的几何。

每个要素至少填写以下属性：

| 字段 | 可用值 | 说明 |
| --- | --- | --- |
| `id` | 唯一文本 | 核验项编号 |
| `source` | `baidu`、`google_earth`、`field`、`official`、`open_data` | 最初发现差异的来源 |
| `observed_on` | `YYYY-MM-DD` | 查看或核实日期 |
| `status` | `pending`、`verified`、`rejected` | 只有 `verified` 才可能改变分析路网 |
| `action` | `review`、`add_path`、`block_path` | `review` 只记录，不改路网 |
| `license_ok` | `true`、`false` | 几何是否可合法用于计算和派生输出 |
| `evidence` | 文本 | 现场记录、正式资料编号或其他依据 |
| `note` | 文本 | 差异说明 |

几何规则：

- `add_path` 使用 `LineString`，两端会在容差内吸附到现有路网节点；
- `block_path` 可使用 `Point` 或 `LineString`，删除最近的双向路段；
- 百度或 Google Earth 只能用于发现疑点时，使用 `status: pending`、`action: review`、`license_ok: false`；
- 经现场、GPS、正式资料或许可相容的开放数据确认后，再新增一条可执行的 `verified` 记录。

示例（仅示范字段，不代表真实场地情况）：

```json
{
  "type": "Feature",
  "geometry": {"type": "Point", "coordinates": [104.14, 30.63]},
  "properties": {
    "id": "review-001",
    "source": "baidu",
    "observed_on": "2026-09-23",
    "status": "pending",
    "action": "review",
    "license_ok": false,
    "evidence": "待现场确认",
    "note": "疑似存在未记录出入口"
  }
}
```

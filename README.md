# Architectural diagram · OSMnx 地图与分析图

使用 [OSMnx](https://github.com/gboeing/osmnx) 从 OpenStreetMap 数据制作的建筑、景观与城市空间分析示例。这里保存的是本地绘图脚本及其已生成的静态图片，**不是 OSMnx 上游项目的 GitHub Fork**，也不是无需设置即可批量出图的通用软件。

## 开始使用

```powershell
python -m pip install -r requirements.txt
python osmnx_kuanzhai_history_planning.py
```

运行环境参考：Python 3.12、OSMnx 2.1.1。脚本第一次获取某区域的路网和设施时需要联网访问 OpenStreetMap 服务；项目中的 PNG 图片可以直接离线查看。`cache/` 是本机 HTTP 响应缓存，不包含在仓库里；若要可靠地**断网重新计算**，还需要提前将所用路网保存为 GraphML、设施图层保存为本地文件，并修改相应脚本从文件读取。

大部分脚本以中国四川省成都市为实例。Windows 系统建议安装“微软雅黑”；其他系统可调整 Matplotlib 中文字体配置。

## 主要图纸

| 地点与主题 | 脚本 | 图纸 |
| --- | --- | --- |
| 宽窄巷子：传统街巷、保护时间轴与二期区位 | `osmnx_kuanzhai_history_planning.py` | `kuanzhai_history_planning.png` |
| 成都东站：15/30 分钟步行可达 | `osmnx_chengdudong_30min.py` | `chengdudong_30min.png` |
| 成都东站：生活圈道路分级 | `osmnx_chengdudong_road_grade.py` | `chengdudong_30min_road_grade_cool.png` |
| 成都东站：生活服务设施 | `osmnx_chengdudong_services.py` | `chengdudong_30min_services.png` |
| 成都东站：换乘步行 | `osmnx_chengdudong_transfer.py` | `chengdudong_transfer_walk.png` |
| 成都东站：绿地与公共空间 | `osmnx_chengdudong_green.py` | `chengdudong_green_access.png` |
| 成都东站：百度地图交互版绿地可达 | `osmnx_chengdudong_baidu_green_data.py` | `chengdudong_baidu_green.html`（联网、需自己的 AK） |
| 成华区：道路方向与密度 | `osmnx_chenghua_orientation_density.py` | `chenghua_road_orientation_density.png` |

仓库还保留了其他探索稿及对应 PNG，供复核和比较。请注意：`osmnx_chenghua.py`、`osmnx_chenghua_orientation.py` 使用的是**近似矩形范围**，不是严格的成华区行政边界；`osmnx_chengdudong_node_density.py` 统计的是步行路网**节点**，不能直接称为经合并处理后的真实路口密度；峨眉山站图仅是局部路网，不是与成都东站同方法计算的生活圈。

## 数据口径与使用边界

- 图中的出行时间多依据网络长度与设定速度**估算**，不是实测步速、实时驾车时间或包含候车时间的公交可达性。
- 宽窄巷子的历史节点来自[成都市文化广电旅游局资料](https://cd3000y.cccic.org.cn/views/3DMuseum/OldStreet.aspx)，二期公开建设规模来自[成都商报 2026-06-17 报道](https://news.chengdu.cn/2026/0617/6a31f160cfd50212c36dcfd6.shtml)。其地图中的二期 OSM 轮廓是位置示意，**不是法定项目红线**；OSM 面积与报道占地并不一致。
- 地图数据 © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)，数据遵循 [ODbL](https://opendatacommons.org/licenses/odbl/1.0/)；OSMnx 软件本身采用 MIT 许可证，二者不能混为一种授权。若将单张 PNG 或加工后的地理数据单独对外发布，也应检查署名和相应许可要求。
- 本仓库不包含百度底图，也不包含授权密钥；接入百度地图时需另行按其条款申请授权，并处理 OSM 坐标与百度地图坐标的差异。

## 百度地图交互版：成都东站绿地与公共空间

已附带导出的 `data/chengdudong_green_access_wgs84.json`；要更新 OSM 分析数据，运行：

```powershell
python osmnx_chengdudong_baidu_green_data.py
```

在项目目录启动本地网页服务（保持该命令运行），然后在浏览器打开对应地址：

```powershell
python -m http.server 8765
```

`http://127.0.0.1:8765/chengdudong_baidu_green.html`

页面先显示原有静态图片；填写**自己的百度地图浏览器端 AK**后，才会联网加载百度底图与可交互图层。本机可选配置 `baidu-map.local.json`（内容格式：`{"ak":"你的浏览器端AK"}`），页面打开时会自动读取并接入；该文件被 `.gitignore` 排除，**不可提交或公开分享**。按[百度官方要求](https://lbs.baidu.com/faq/details?id=2320&title=2787)为访问网页的地址配置 AK 的 Referer 白名单；百度[支持 IPv4 地址](https://lbs.baidu.com/faq/details?id=2294&title=2590)，本地调试可为 `127.0.0.1` 配置白名单并访问 `http://127.0.0.1:8765/chengdudong_baidu_green.html`。若仍无法通过校验，就部署到已授权的网页域名验证。浏览器端 AK 会随网页请求发送给百度，需做好来源限制。静态预览图**不是**百度底图。

此网页调用百度 JS API 4.0 的 WGS84 覆盖物能力，把导出的 OSM 路网和设施几何叠到在线百度底图上；计算使用原始路网坐标，并非百度路线规划。百度底图是否能显示仍取决于**浏览器端** AK、JavaScript API 服务权限、来源白名单和网络。百度错误码 210 表示 APP IP 校验失败，须到控制台核对 AK 类型；不要把疑似服务端 AK 直接放进可被浏览器读取的配置文件。

## OSM、百度地图与 Google Earth 三源核验

三源流程以 OSM 为可计算主骨架，把百度地图和 Google Earth 用作差异发现与人工核验界面。原始 OSM 快照始终保留；只有标记为 `verified` 且 `license_ok: true` 的本地修正才会进入分析图，避免把未经确认或许可不明的专有地图内容直接复制进路网。

先运行离线自检，再运行真实场地：

```powershell
python osm_three_source_workflow.py self-test
python osm_three_source_workflow.py run
```

首次真实运行会下载成都东站步行路网并保存固定快照；以后默认复用该快照。只有明确需要更新 OSM 数据时才运行：

```powershell
python osm_three_source_workflow.py run --refresh
```

主要文件：

- `data/crosscheck_config.json`：项目坐标、范围、步速和输出路径；
- `data/review/chengdudong_observations.geojson`：三源差异及核验状态；
- `data/review/README.md`：字段、许可门槛和几何规则；
- `data/osm/`：原始与核验后 GraphML，本地生成且不提交；
- `data/results/chengdudong_crosscheck_audit.json`：每条核验项是否应用及前后指标；
- `chengdudong_crosscheck.png`：原始 OSM 与核验后 30 分钟路网对比。

`osmnx_chengdudong_30min.py` 已接入核验后的固定路网。当前其他专题图仍沿用原脚本，待这条主链路验证稳定后再逐项迁移。

成都南站使用独立配置运行，不会覆盖成都东站数据：

```powershell
python osm_three_source_workflow.py run --config data/chengdunan_crosscheck_config.json
python osmnx_chengdudong_30min.py --config data/chengdunan_crosscheck_config.json
python osmnx_chengdudong_green.py --config data/chengdunan_crosscheck_config.json
```

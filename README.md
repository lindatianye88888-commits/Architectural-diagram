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
| 成华区：道路方向与密度 | `osmnx_chenghua_orientation_density.py` | `chenghua_road_orientation_density.png` |

仓库还保留了其他探索稿及对应 PNG，供复核和比较。请注意：`osmnx_chenghua.py`、`osmnx_chenghua_orientation.py` 使用的是**近似矩形范围**，不是严格的成华区行政边界；`osmnx_chengdudong_node_density.py` 统计的是步行路网**节点**，不能直接称为经合并处理后的真实路口密度；峨眉山站图仅是局部路网，不是与成都东站同方法计算的生活圈。

## 数据口径与使用边界

- 图中的出行时间多依据网络长度与设定速度**估算**，不是实测步速、实时驾车时间或包含候车时间的公交可达性。
- 宽窄巷子的历史节点来自[成都市文化广电旅游局资料](https://cd3000y.cccic.org.cn/views/3DMuseum/OldStreet.aspx)，二期公开建设规模来自[成都商报 2026-06-17 报道](https://news.chengdu.cn/2026/0617/6a31f160cfd50212c36dcfd6.shtml)。其地图中的二期 OSM 轮廓是位置示意，**不是法定项目红线**；OSM 面积与报道占地并不一致。
- 地图数据 © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)，数据遵循 [ODbL](https://opendatacommons.org/licenses/odbl/1.0/)；OSMnx 软件本身采用 MIT 许可证，二者不能混为一种授权。若将单张 PNG 或加工后的地理数据单独对外发布，也应检查署名和相应许可要求。
- 本仓库不包含百度底图，也不包含授权密钥；接入百度地图时需另行按其条款申请授权，并处理 OSM 坐标与百度地图坐标的差异。

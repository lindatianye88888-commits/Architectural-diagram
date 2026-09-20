"""
成都东站 30 分钟步行生活圈 · 道路分级版（需联网 → dangerouslyDisableSandbox 运行）
在 30 分钟可达范围里，把步行路网按 OSM 道路等级分三级着色：
  1) 城市干道/次干道  primary·secondary·tertiary（及 link）
  2) 街道/支路        residential·living_street·unclassified·road·service
  3) 步行专用路/小径  pedestrian·footway·path·cycleway·steps·track ...
15 分钟核心区用底色叠加，便于看"核心—外围"层级。
"""
import collections
import os
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import LineString
from shapely.ops import substring

ROOT = Path(__file__).resolve().parent
LAT, LON = 30.6308, 104.1411
WALK_SPEED_M_S = 4.8 * 1000 / 3600
SEARCH_RADIUS_M = 3000
BAND_WIDTH_M = 35

# 显式注册中文字体，确保中文标题/图例正常渲染
import matplotlib
from matplotlib import font_manager as _fm
_CJK_FONT = "C:/Windows/Fonts/msyh.ttc"
if os.path.exists(_CJK_FONT):
    _fm.fontManager.addfont(_CJK_FONT)
    _CJK_NAME = _fm.FontProperties(fname=_CJK_FONT).get_name()
    plt.rcParams["font.family"] = _CJK_NAME
else:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans SC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

# 道路等级配色（低饱和大地色）
LEVEL_COLORS = {1: "#3c4f43", 2: "#6f8d79", 3: "#a7c0ad"}
LEVEL_WIDTHS = {1: 1.8, 2: 1.05, 3: 0.6}
LEVEL_LABELS = {1: "城市干道 / 次干道", 2: "街道 / 支路", 3: "步行专用路 / 小径"}

_MAJOR = {"primary", "primary_link", "secondary", "secondary_link",
          "tertiary", "tertiary_link", "trunk", "trunk_link"}
_STREET = {"residential", "living_street", "unclassified", "road", "service"}
_PED = {"pedestrian", "footway", "path", "cycleway", "steps", "track",
        "corridor", "bridleway", "platform"}


def classify(highway):
    if isinstance(highway, list):
        hw = highway
    elif isinstance(highway, str):
        hw = [highway]
    else:
        return 3
    for h in hw:
        if h in _MAJOR:
            return 1
    for h in hw:
        if h in _STREET:
            return 2
    return 3


def reachable_lines_classified(graph, durations, seconds):
    """返回 (line, level, length) 列表，路段做局部截断以贴合'刚好 N 分钟走到哪'。"""
    items = []
    for u, v, data in graph.edges(data=True):
        remaining = seconds - durations.get(u, float("inf"))
        if remaining <= 0:
            continue
        line = data.get("geometry") or LineString(
            [(graph.nodes[u]["x"], graph.nodes[u]["y"]),
             (graph.nodes[v]["x"], graph.nodes[v]["y"])]
        )
        ux, uy = graph.nodes[u]["x"], graph.nodes[u]["y"]
        if (line.coords[-1][0] - ux) ** 2 + (line.coords[-1][1] - uy) ** 2 < (
            (line.coords[0][0] - ux) ** 2 + (line.coords[0][1] - uy) ** 2
        ):
            line = LineString(list(line.coords)[::-1])
        fraction = min(1, remaining * WALK_SPEED_M_S / data["length"])
        if fraction < 1:
            line = substring(line, 0, fraction, normalized=True)
        if line.geom_type == "LineString" and line.length > 0:
            items.append((line, classify(data.get("highway", "?")), line.length))
    return items


def main():
    print("获取成都东站周边步行路网（首次运行需连接 OpenStreetMap）……", flush=True)
    graph = ox.graph_from_point((LAT, LON), dist=SEARCH_RADIUS_M, network_type="walk")
    graph = ox.project_graph(graph)
    crs = graph.graph["crs"]
    station = gpd.GeoSeries(gpd.points_from_xy([LON], [LAT]), crs="EPSG:4326").to_crs(crs).iloc[0]
    origin = min(
        graph.nodes,
        key=lambda n: (graph.nodes[n]["x"] - station.x) ** 2
        + (graph.nodes[n]["y"] - station.y) ** 2,
    )
    offset_m = station.distance(
        gpd.GeoSeries(gpd.points_from_xy([graph.nodes[origin]["x"]],
                                         [graph.nodes[origin]["y"]])).iloc[0]
    )
    for _, _, data in graph.edges(data=True):
        data["travel_time"] = data["length"] / WALK_SPEED_M_S
    durations = nx.single_source_dijkstra_path_length(graph, origin, cutoff=30 * 60, weight="travel_time")

    print(f"路网：{len(graph):,} 个节点；起点离站点标记约 {offset_m:.0f} 米", flush=True)

    items30 = reachable_lines_classified(graph, durations, 30 * 60)
    lines30 = [it[0] for it in items30]
    roads30 = gpd.GeoSeries(lines30, crs=crs).union_all()
    band30 = gpd.GeoSeries([roads30.buffer(BAND_WIDTH_M)], crs=crs)

    items15 = reachable_lines_classified(graph, durations, 15 * 60)
    lines15 = [it[0] for it in items15]
    roads15 = gpd.GeoSeries(lines15, crs=crs).union_all()
    band15 = gpd.GeoSeries([roads15.buffer(BAND_WIDTH_M)], crs=crs)

    # 各级道路长度 / 段数
    level_len = collections.defaultdict(float)
    level_cnt = collections.defaultdict(int)
    for _, lvl, ln in items30:
        level_len[lvl] += ln
        level_cnt[lvl] += 1
    reached30 = sum(t <= 30 * 60 for t in durations.values())
    reached15 = sum(t <= 15 * 60 for t in durations.values())
    print(f"30 分钟可达节点 {reached30:,}；道路带 {band30.area.iloc[0]/1e6:.2f} km²", flush=True)
    for lvl in (1, 2, 3):
        print(f"  L{lvl} {LEVEL_LABELS[lvl]}：{level_cnt[lvl]:,} 段 / {level_len[lvl]/1000:.1f} km", flush=True)

    background = ox.graph_to_gdfs(graph, nodes=False)["geometry"]
    fig, ax = plt.subplots(figsize=(12, 12), dpi=180)
    fig.patch.set_facecolor("#eef1ec")
    ax.set_facecolor("#eef1ec")
    fig.subplots_adjust(left=0.035, right=0.965, top=0.86, bottom=0.155)

    background.plot(ax=ax, color="#d6dbd4", linewidth=0.42, zorder=1)
    band30.plot(ax=ax, facecolor="#b6c8b8", edgecolor="none", alpha=0.42, zorder=2)
    band15.plot(ax=ax, facecolor="#7e9f8b", edgecolor="none", alpha=0.40, zorder=3)

    # 30 分钟可达道路按等级着色
    for lvl in (3, 2, 1):  # 先画细的，再铺粗的，粗线在上
        segs = [it[0] for it in items30 if it[1] == lvl]
        if not segs:
            continue
        gpd.GeoSeries(segs, crs=crs).plot(
            ax=ax, color=LEVEL_COLORS[lvl], linewidth=LEVEL_WIDTHS[lvl], zorder=4 + lvl)

    ax.scatter(station.x, station.y, c="#2f3d35", s=135, marker="*",
               edgecolors="white", linewidth=1.1, zorder=9)
    ax.annotate("成都东站", (station.x, station.y), xytext=(10, 9),
                textcoords="offset points", fontsize=12, weight="bold",
                color="#2f3d35", zorder=10)

    span = SEARCH_RADIUS_M * 1.04
    ax.set_xlim(station.x - span, station.x + span)
    ax.set_ylim(station.y - span, station.y + span)
    ax.set_aspect("equal")
    ax.axis("off")

    fig.text(0.065, 0.955, "成都东站 · 30 分钟步行生活圈 · 道路分级",
             fontsize=22, weight="bold", color="#37463c", va="top")
    fig.text(0.066, 0.915, "沿开放街图步行道路按等级着色   /   深绿=15 分钟核心区，浅绿=30 分钟范围",
             fontsize=11, color="#5f7264", va="top")

    handles = [
        Patch(facecolor="#7e9f8b", edgecolor="none", label="15 分钟核心区"),
        Patch(facecolor="#b6c8b8", edgecolor="none", label="30 分钟可达范围"),
        Line2D([], [], color=LEVEL_COLORS[1], lw=LEVEL_WIDTHS[1], label=f"L1 {LEVEL_LABELS[1]}（{level_len[1]/1000:.0f} km）"),
        Line2D([], [], color=LEVEL_COLORS[2], lw=LEVEL_WIDTHS[2], label=f"L2 {LEVEL_LABELS[2]}（{level_len[2]/1000:.0f} km）"),
        Line2D([], [], color=LEVEL_COLORS[3], lw=LEVEL_WIDTHS[3], label=f"L3 {LEVEL_LABELS[3]}（{level_len[3]/1000:.0f} km）"),
        Line2D([], [], marker="*", linestyle="", markerfacecolor="#2f3d35",
               markeredgecolor="white", markersize=13, label="成都东站"),
    ]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.065, 0.035),
               ncol=2, frameon=False, fontsize=10, labelcolor="#37463c")
    fig.text(0.067, 0.115,
             f"步速 4.8 km/h · 30 分钟可达 {reached30:,} 个路口 / 路网 {level_len[1]+level_len[2]+level_len[3]:.0f} km"
             f" · 站点取最近路网节点（偏移约 {offset_m:.0f} m）",
             fontsize=9, color="#5f7264")
    fig.text(0.067, 0.092,
             "色带为可达道路两侧 35 m 示意，非全部街区均可达；道路等级按 OSM highway 标签划分，未计过街等待。",
             fontsize=9, color="#5f7264")
    fig.text(0.067, 0.068, "道路数据 © OpenStreetMap contributors  |  计算：OSMnx / NetworkX",
             fontsize=8.5, color="#9aa89c")

    output = ROOT / "chengdudong_30min_classified.png"
    fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"已保存：{output}", flush=True)


if __name__ == "__main__":
    main()

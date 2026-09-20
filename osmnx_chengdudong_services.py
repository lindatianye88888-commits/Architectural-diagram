"""成都东站 30 分钟步行圈的生活服务设施分布图。

运行：python osmnx_chengdudong_services.py
设施来自 OpenStreetMap；可达性按设施代表点到最近路网节点估算，非实测入口路线。
"""

from collections import Counter

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.spatial import cKDTree
from shapely.geometry import Point

from osmnx_chengdudong_30min import (
    BAND_WIDTH_M,
    LAT,
    LON,
    ROOT,
    SEARCH_RADIUS_M,
    WALK_SPEED_M_S,
    reachable_lines,
)


CATEGORIES = {
    "dining": {"name": "餐饮", "color": "#526FA4"},
    "shopping": {"name": "购物", "color": "#2293A2"},
    "health": {"name": "医疗／药店", "color": "#AC527E"},
    "education": {"name": "教育", "color": "#7963AB"},
    "green": {"name": "公园休闲", "color": "#358E68"},
}
TAGS = {
    "amenity": ["restaurant", "cafe", "fast_food", "food_court", "pharmacy",
                "hospital", "clinic", "doctors", "school", "kindergarten"],
    "shop": ["supermarket", "convenience", "mall"],
    "leisure": ["park", "garden", "playground"],
}


def category(row):
    if row.get("amenity") in {"restaurant", "cafe", "fast_food", "food_court"}:
        return "dining"
    if row.get("shop") in {"supermarket", "convenience", "mall"}:
        return "shopping"
    if row.get("amenity") in {"pharmacy", "hospital", "clinic", "doctors"}:
        return "health"
    if row.get("amenity") in {"school", "kindergarten"}:
        return "education"
    if row.get("leisure") in {"park", "garden", "playground"}:
        return "green"
    return None


def main():
    print("读取步行路网及周边设施……", flush=True)
    graph = ox.project_graph(
        ox.graph_from_point((LAT, LON), dist=SEARCH_RADIUS_M, network_type="walk")
    )
    crs = graph.graph["crs"]
    station = gpd.GeoSeries([Point(LON, LAT)], crs="EPSG:4326").to_crs(crs).iloc[0]
    node_ids = list(graph.nodes)
    positions = np.asarray([(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in node_ids])
    index = cKDTree(positions)
    _, origin_pos = index.query([station.x, station.y])
    origin = node_ids[origin_pos]
    for _, _, data in graph.edges(data=True):
        data["travel_time"] = data["length"] / WALK_SPEED_M_S
    walk_times = nx.single_source_dijkstra_path_length(
        graph, origin, cutoff=30 * 60, weight="travel_time"
    )
    roads_15 = gpd.GeoSeries(
        [gpd.GeoSeries(reachable_lines(graph, walk_times, 15 * 60), crs=crs).union_all()],
        crs=crs,
    )
    roads_30 = gpd.GeoSeries(
        [gpd.GeoSeries(reachable_lines(graph, walk_times, 30 * 60), crs=crs).union_all()],
        crs=crs,
    )

    facilities = ox.features_from_point((LAT, LON), TAGS, dist=SEARCH_RADIUS_M)
    facilities = facilities.loc[facilities.geometry.notna() & ~facilities.geometry.is_empty]
    facilities = facilities.to_crs(crs).copy()
    facilities["kind"] = facilities.apply(category, axis=1)
    facilities = facilities[facilities.kind.notna()].copy()
    # 大型公园等面状设施用面内代表点；此估计不是园区实际出入口距离。
    facilities["point"] = facilities.geometry.representative_point()
    xy = np.array([(p.x, p.y) for p in facilities.point])
    straight_m, nearest_idx = index.query(xy)
    facilities["snap_m"] = straight_m
    facilities["walk_min"] = [
        (walk_times.get(node_ids[i], float("inf")) + d / WALK_SPEED_M_S) / 60
        for i, d in zip(nearest_idx, straight_m)
    ]
    # 离记录路网太远的设施不判断为可达，以免把跨铁路/地块的直线当成道路。
    facilities["reachable"] = (facilities.snap_m <= 200) & (facilities.walk_min <= 30)
    display_points = gpd.GeoDataFrame(
        facilities.drop(columns="geometry"), geometry="point", crs=crs
    )
    stats = Counter(display_points.loc[display_points.reachable, "kind"])
    totals = Counter(display_points.kind)
    print(f"设施记录 {len(display_points)}，估算 30 分钟内 {sum(stats.values())}", flush=True)
    for key, style in CATEGORIES.items():
        print(f"{style['name']}: {stats[key]} / {totals[key]}", flush=True)

    fig, ax = plt.subplots(figsize=(12, 12), dpi=180)
    fig.patch.set_facecolor("#F9FBFD")
    ax.set_facecolor("#F9FBFD")
    fig.subplots_adjust(left=0.035, right=0.965, top=0.86, bottom=0.20)
    ox.graph_to_gdfs(graph, nodes=False).geometry.plot(
        ax=ax, color="#DCE3E9", linewidth=0.48, zorder=1
    )
    roads_30.buffer(BAND_WIDTH_M).plot(
        ax=ax, facecolor="#C7E1F2", edgecolor="none", alpha=0.43, zorder=2
    )
    roads_15.buffer(BAND_WIDTH_M).plot(
        ax=ax, facecolor="#9CB9DF", edgecolor="none", alpha=0.40, zorder=3
    )
    roads_30.plot(ax=ax, color="#83A7C2", linewidth=0.72, alpha=0.78, zorder=4)
    roads_15.plot(ax=ax, color="#506F9D", linewidth=0.85, alpha=0.85, zorder=5)
    outside = display_points[~display_points.reachable]
    if len(outside):
        outside.plot(ax=ax, color="#9DA9B5", markersize=13, alpha=0.40,
                     edgecolor="white", linewidth=0.2, zorder=6)
    for key, style in CATEGORIES.items():
        selected = display_points[(display_points.kind == key) & display_points.reachable]
        if len(selected):
            selected.plot(ax=ax, color=style["color"], markersize=43,
                          alpha=0.95, edgecolor="white", linewidth=0.55, zorder=7)

    ax.scatter(station.x, station.y, c="#1B3553", s=150, marker="*",
               edgecolors="white", linewidth=1.25, zorder=9)
    ax.annotate("成都东站", (station.x, station.y), xytext=(9, 8),
                textcoords="offset points", fontsize=12, weight="bold",
                color="#1B3553", zorder=10)
    span = SEARCH_RADIUS_M * 1.04
    ax.set_xlim(station.x - span, station.x + span)
    ax.set_ylim(station.y - span, station.y + span)
    ax.set_aspect("equal")
    ax.axis("off")

    fig.text(0.065, 0.955, "成都东站 · 30 分钟生活服务设施图",
             fontsize=22, weight="bold", color="#213B52", va="top")
    fig.text(0.066, 0.913,
             f"OpenStreetMap 周边设施 {len(display_points)} 条   /   估算步行 30 分钟内 {sum(stats.values())} 条",
             fontsize=11, color="#5D7181", va="top")
    handles = [
        Line2D([], [], marker="o", linestyle="", markersize=8,
               markerfacecolor=style["color"], markeredgecolor="white",
               label=f"{style['name']}  {stats[key]} / {totals[key]}")
        for key, style in CATEGORIES.items()
    ]
    handles += [
        Patch(facecolor="#9CB9DF", alpha=0.55, edgecolor="none", label="15 分钟可达带"),
        Patch(facecolor="#C7E1F2", edgecolor="none", label="30 分钟可达带"),
        Line2D([], [], marker="o", linestyle="", markerfacecolor="#9DA9B5",
               markeredgecolor="white", markersize=7, label="圈外设施记录"),
    ]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.066, 0.123),
               ncol=3, fontsize=9.3, frameon=False, labelcolor="#213B52",
               columnspacing=1.8)
    fig.text(0.067, 0.099, "图例数字：估算圈内 / 研究范围内；同址多条 OSM 记录分别计数，未去重为独立门店。",
             fontsize=8.5, color="#5D7181")
    fig.text(0.067, 0.075,
             "可达性按设施代表点吸附最近路口估算（距离超过 200 m 不计圈内）；未核实出入口、跨路障碍及营业状态。",
             fontsize=8.4, color="#5D7181")
    fig.text(0.067, 0.050, "数据 © OpenStreetMap contributors  |  路网及设施可能漏标  |  计算：OSMnx / NetworkX",
             fontsize=8.3, color="#788B9A")
    output = ROOT / "chengdudong_30min_services.png"
    fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"已保存：{output}", flush=True)


if __name__ == "__main__":
    main()

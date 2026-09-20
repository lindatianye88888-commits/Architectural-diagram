"""成都东站 30 分钟步行圈内道路的 OSM 标签分组图。

运行：python osmnx_chengdudong_road_grade.py
分组是为了展示道路用途/网络角色，不是法定道路等级或步行环境评估。
"""

from collections import defaultdict

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import Point

from osmnx_chengdudong_30min import (
    BAND_WIDTH_M,
    LAT,
    LON,
    ROOT,
    SEARCH_RADIUS_M,
    WALK_SPEED_M_S,
    reachable_segments,
)


GROUPS = {
    "arterial": {"label": "主干道路", "color": "#233F70", "width": 2.3},
    "collector": {"label": "次级连接道路", "color": "#387EB5", "width": 1.8},
    "local": {"label": "街坊／服务道路", "color": "#8099B5", "width": 1.45},
    "pedestrian": {"label": "步行专用／小径", "color": "#087F75", "width": 1.45},
    "other": {"label": "其他已标注道路", "color": "#687689", "width": 1.2},
}
TAGS = {
    "arterial": {"trunk", "trunk_link", "primary", "primary_link"},
    "collector": {"secondary", "secondary_link", "tertiary", "tertiary_link"},
    "local": {"residential", "unclassified", "service", "living_street"},
    "pedestrian": {"footway", "pedestrian", "path", "steps", "corridor", "track", "bridleway", "cycleway"},
}


def road_group(value):
    """简化图中不同 highway 标签可能合并为列表，按最高道路角色分组。"""
    values = set(value if isinstance(value, list) else [value])
    for group, tags in TAGS.items():
        if values & tags:
            return group
    return "other"


def main():
    print("读取成都东站周边的步行路网……", flush=True)
    graph = ox.project_graph(
        ox.graph_from_point((LAT, LON), dist=SEARCH_RADIUS_M, network_type="walk")
    )
    crs = graph.graph["crs"]
    station = gpd.GeoSeries(gpd.points_from_xy([LON], [LAT]), crs="EPSG:4326").to_crs(crs).iloc[0]
    origin = min(graph.nodes, key=lambda n:
                 (graph.nodes[n]["x"] - station.x) ** 2 +
                 (graph.nodes[n]["y"] - station.y) ** 2)
    for _, _, edge in graph.edges(data=True):
        edge["travel_time"] = edge["length"] / WALK_SPEED_M_S
    times = nx.single_source_dijkstra_path_length(
        graph, origin, cutoff=1800, weight="travel_time"
    )

    geometries = defaultdict(list)
    for line, edge in reachable_segments(graph, times, 1800):
        geometries[road_group(edge.get("highway"))].append(line)
    if not geometries:
        raise RuntimeError("没有发现 30 分钟内的可达道路。")

    accessible_30 = gpd.GeoSeries(
        [line for lines in geometries.values() for line in lines], crs=crs
    ).union_all()
    accessible_15 = gpd.GeoSeries(
        [line for line, _ in reachable_segments(graph, times, 900)], crs=crs
    ).union_all()

    fig, ax = plt.subplots(figsize=(12, 12), dpi=180)
    fig.patch.set_facecolor("#F9FBFD")
    ax.set_facecolor("#F9FBFD")
    fig.subplots_adjust(left=0.035, right=0.965, top=0.86, bottom=0.19)
    ox.graph_to_gdfs(graph, nodes=False).geometry.plot(
        ax=ax, color="#DCE3E9", linewidth=0.50, zorder=1
    )
    gpd.GeoSeries([accessible_30.buffer(BAND_WIDTH_M)], crs=crs).plot(
        ax=ax, facecolor="#C7E1F2", edgecolor="none", alpha=0.55, zorder=2
    )
    gpd.GeoSeries([accessible_15.buffer(BAND_WIDTH_M)], crs=crs).plot(
        ax=ax, facecolor="#9CB9DF", edgecolor="none", alpha=0.32, zorder=3
    )

    handles = []
    for group, style in GROUPS.items():
        if not geometries[group]:
            continue
        physical_roads = gpd.GeoSeries(geometries[group], crs=crs).union_all()
        gpd.GeoSeries([physical_roads], crs=crs).plot(
            ax=ax, color=style["color"], linewidth=style["width"], zorder=4
        )
        distance_km = physical_roads.length / 1000
        print(f"{style['label']}: {distance_km:.1f} km", flush=True)
        handles.append(Line2D([], [], color=style["color"], lw=style["width"] + 0.6,
                              label=f"{style['label']} · {distance_km:.1f} km"))

    ax.scatter(station.x, station.y, c="#1B3553", s=145, marker="*",
               edgecolors="white", linewidth=1.3, zorder=7)
    ax.annotate("成都东站", (station.x, station.y), xytext=(9, 8),
                textcoords="offset points", fontsize=12, weight="bold",
                color="#1B3553", zorder=8)
    span = SEARCH_RADIUS_M * 1.04
    ax.set_xlim(station.x - span, station.x + span)
    ax.set_ylim(station.y - span, station.y + span)
    ax.set_aspect("equal")
    ax.axis("off")

    fig.text(0.065, 0.955, "成都东站 · 30 分钟步行圈道路分级",
             fontsize=23, weight="bold", color="#213B52", va="top")
    fig.text(0.066, 0.912, "按 OpenStreetMap highway 标签分组  /  仅对步行可达道路着色",
             fontsize=11, color="#5D7181", va="top")
    handles += [
        Patch(facecolor="#9CB9DF", alpha=0.48, edgecolor="none", label="15 分钟可达带"),
        Patch(facecolor="#C7E1F2", edgecolor="none", label="30 分钟可达带"),
    ]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.066, 0.124),
               ncol=2, fontsize=9.5, frameon=False, labelcolor="#213B52",
               columnspacing=3.0)
    fig.text(0.067, 0.097,
             "标签归并：trunk/primary→主干；secondary/tertiary→次级；residential/service 等→街坊；footway/path 等→步行。",
             fontsize=8.2, color="#5D7181")
    fig.text(0.067, 0.073,
             "OSM 道路角色≠法定道路等级；可步行道路标签亦不保证现场可安全通行。步速 4.8 km/h，色带为道路两侧 35 m 示意。",
             fontsize=8.2, color="#5D7181")
    fig.text(0.067, 0.048, "道路数据 © OpenStreetMap contributors  |  计算：OSMnx / NetworkX",
             fontsize=8.2, color="#788B9A")
    output = ROOT / "chengdudong_30min_road_grade_cool.png"
    fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"已保存：{output}", flush=True)


if __name__ == "__main__":
    main()

"""车站步行 15/30 分钟路网可达范围图。

默认运行成都东站；也可以传入其他三源核验配置：
    python osmnx_chengdudong_30min.py --config data/chengdunan_crosscheck_config.json
"""

import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import LineString, Point
from shapely.ops import substring

from osm_three_source_workflow import (
    DEFAULT_CONFIG,
    build_verified_graph,
    load_config,
    resolve_path,
)


ROOT = Path(__file__).resolve().parent
LAT, LON = 30.6308, 104.1411
WALK_SPEED_M_S = 4.8 * 1000 / 3600
SEARCH_RADIUS_M = 3000  # 高于 30 分钟理论直线极限 2400 m，避免地图边缘截断
BAND_WIDTH_M = 35  # 仅用于绘图：对实际可达路段两侧各扩展 35 米

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans SC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
ox.settings.timeout = 600
ox.settings.use_cache = True
ox.settings.cache_folder = str(ROOT / "cache")


def reachable_segments(graph, durations, seconds, walk_speed_m_s=WALK_SPEED_M_S):
    """逐条有向路段截取可达部分，同时保留原始道路标签。"""
    segments = []
    for u, v, data in graph.edges(data=True):
        remaining = seconds - durations.get(u, float("inf"))
        if remaining <= 0:
            continue
        line = data.get("geometry") or LineString(
            [(graph.nodes[u]["x"], graph.nodes[u]["y"]),
             (graph.nodes[v]["x"], graph.nodes[v]["y"])]
        )
        # 简化后的 OSM 边含曲线；其 geometry 的点序不一定与有向边一致。
        ux, uy = graph.nodes[u]["x"], graph.nodes[u]["y"]
        if (line.coords[-1][0] - ux) ** 2 + (line.coords[-1][1] - uy) ** 2 < (
            (line.coords[0][0] - ux) ** 2 + (line.coords[0][1] - uy) ** 2
        ):
            line = LineString(list(line.coords)[::-1])
        fraction = min(1, remaining * walk_speed_m_s / data["length"])
        if fraction < 1:
            line = substring(line, 0, fraction, normalized=True)
        if line.geom_type == "LineString" and line.length > 0:
            segments.append((line, data))
    return segments


def reachable_lines(graph, durations, seconds, walk_speed_m_s=WALK_SPEED_M_S):
    """返回可达路段的几何；包含终点路段的局部长度。"""
    return [
        line
        for line, _ in reachable_segments(
            graph, durations, seconds, walk_speed_m_s=walk_speed_m_s
        )
    ]


def main(config_path=DEFAULT_CONFIG):
    config = load_config(config_path)
    title = config.get("title", config["project_id"])
    lat = float(config["center"]["lat"])
    lon = float(config["center"]["lon"])
    search_radius_m = float(config["search_radius_m"])
    walk_speed_kmh = float(config.get("walk_speed_kmh", 4.8))
    walk_speed_m_s = walk_speed_kmh * 1000 / 3600
    minutes_values = [int(value) for value in config.get("analysis_minutes", [15, 30])]
    if minutes_values != [15, 30]:
        raise ValueError("当前版式要求 analysis_minutes 为 [15, 30]。")

    print(f"加载{title} OSM 底板与三源核验修正层……", flush=True)
    graph, crosscheck = build_verified_graph(config_path)
    crs = graph.graph["crs"]
    station = gpd.GeoSeries(gpd.points_from_xy([lon], [lat]), crs="EPSG:4326").to_crs(crs).iloc[0]
    origin = min(
        graph.nodes,
        key=lambda n: (graph.nodes[n]["x"] - station.x) ** 2
        + (graph.nodes[n]["y"] - station.y) ** 2,
    )
    offset_m = station.distance(Point(graph.nodes[origin]["x"], graph.nodes[origin]["y"]))
    for _, _, data in graph.edges(data=True):
        data["travel_time"] = data["length"] / walk_speed_m_s
    durations = nx.single_source_dijkstra_path_length(
        graph, origin, cutoff=30 * 60, weight="travel_time"
    )

    print(
        f"路网：{len(graph):,} 个节点；起点离站点标记约 {offset_m:.0f} 米；"
        f"已应用核验修正 {crosscheck['applied_count']} 条",
        flush=True,
    )
    bands = {}
    road_lines = {}
    for minutes in (15, 30):
        lines = reachable_lines(
            graph, durations, minutes * 60, walk_speed_m_s=walk_speed_m_s
        )
        if not lines:
            raise RuntimeError(f"没有找到 {minutes} 分钟可达的步行道路。")
        roads = gpd.GeoSeries(lines, crs=crs).union_all()
        road_lines[minutes] = gpd.GeoSeries([roads], crs=crs)
        bands[minutes] = gpd.GeoSeries([roads.buffer(BAND_WIDTH_M)], crs=crs)
        reached = sum(t <= minutes * 60 for t in durations.values())
        print(
            f"{minutes} 分钟：可达节点 {reached:,}；"
            f"去重路段约 {roads.length / 1000:.1f} km；"
            f"道路带面积约 {bands[minutes].area.iloc[0] / 1e6:.2f} km2",
            flush=True,
        )

    background = ox.graph_to_gdfs(graph, nodes=False)["geometry"]
    fig, ax = plt.subplots(figsize=(12, 12), dpi=180)
    fig.patch.set_facecolor("#fbf9f4")
    ax.set_facecolor("#fbf9f4")
    fig.subplots_adjust(left=0.035, right=0.965, top=0.86, bottom=0.18)

    background.plot(ax=ax, color="#dad8d1", linewidth=0.42, zorder=1)
    bands[30].plot(ax=ax, facecolor="#e5ba76", edgecolor="none", alpha=0.43, zorder=2)
    bands[15].plot(ax=ax, facecolor="#c67652", edgecolor="none", alpha=0.42, zorder=3)
    road_lines[30].plot(ax=ax, color="#bb8650", linewidth=0.8, zorder=4)
    road_lines[15].plot(ax=ax, color="#934a37", linewidth=1.25, zorder=5)

    ax.scatter(station.x, station.y, c="#73342e", s=135, marker="*",
               edgecolors="white", linewidth=1.1, zorder=7)
    ax.annotate(title, (station.x, station.y), xytext=(10, 9),
                textcoords="offset points", fontsize=12, weight="bold",
                color="#73342e", zorder=8,
                path_effects=[])

    # 把范围锁定在站点周围，保留少许留白，不依赖几何的自动缩放。
    span = search_radius_m * 1.04
    ax.set_xlim(station.x - span, station.x + span)
    ax.set_ylim(station.y - span, station.y + span)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.text(0.065, 0.955, f"{title} · 30 分钟步行生活圈",
             fontsize=23, weight="bold", color="#513b31", va="top")
    fig.text(0.066, 0.912, "基于固定 OSM 底板及已确认修正计算最短通行时间   /   15 分钟圈叠加对照",
             fontsize=11, color="#786b61", va="top")
    handles = [
        Patch(facecolor="#d99366", edgecolor="none", label="15 分钟可达道路带"),
        Patch(facecolor="#e5ba76", edgecolor="none", label="30 分钟可达道路带"),
        Line2D([], [], color="#dad8d1", lw=1.3, label="其他步行路网"),
        Line2D([], [], marker="*", linestyle="", markerfacecolor="#73342e",
               markeredgecolor="white", markersize=13, label=title),
    ]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.065, 0.124),
               ncol=2, frameon=False, fontsize=10, labelcolor="#513b31")
    fig.text(0.067, 0.102,
             f"步速 {walk_speed_kmh:g} km/h · 路网距离计算 · 站点取最近路网节点（偏移约 {offset_m:.0f} m）",
             fontsize=9, color="#786b61")
    fig.text(0.067, 0.078,
             "色带为可达道路两侧 35 m 示意，非全部街区均可达；未计道路外通行、候车和过街等待。",
             fontsize=9, color="#786b61")
    fig.text(0.067, 0.054,
             f"道路数据 © OpenStreetMap contributors  |  三源核验修正 {crosscheck['applied_count']} 条  |  OSMnx / NetworkX",
             fontsize=8.5, color="#8c8073")

    output = resolve_path(
        config["paths"].get("analysis_png", f"{config['project_id']}_30min.png")
    )
    fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"已保存：{output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    main(args.config)

"""成都东站步行换乘示意：从站点定位点到地铁出入口和公交站的道路最短路径。"""

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
from matplotlib.lines import Line2D
from scipy.spatial import cKDTree
from shapely.geometry import Point

from osmnx_chengdudong_30min import (
    LAT, LON, ROOT, SEARCH_RADIUS_M, WALK_SPEED_M_S,
)


TAGS = {
    "railway": ["subway_entrance", "station"],
    "highway": "bus_stop",
    "public_transport": "platform",
    "amenity": "bus_station",
}
FOCUS_M = 1050
COLORS = {"metro": "#16847D", "bus": "#7A5DA6"}


def transit_mode(feature):
    if feature.get("railway") == "subway_entrance":
        return "metro"
    if feature.get("highway") == "bus_stop" or feature.get("amenity") == "bus_station":
        return "bus"
    if feature.get("public_transport") == "platform" and feature.get("bus") == "yes":
        return "bus"
    return None


def label(feature):
    if feature["mode"] == "metro":
        entrance = feature.get("ref")
        if not isinstance(entrance, str) or not entrance.strip():
            entrance = feature.get("name")
        if not isinstance(entrance, str) or not entrance.strip():
            entrance = ""
        return f"地铁口 {entrance.strip()}"[:16]
    bus_name = feature.get("name")
    if not isinstance(bus_name, str) or not bus_name.strip():
        bus_name = "公交站"
    return bus_name.strip()[:12]


def main():
    print("读取成都东站步行路网及公交/地铁点位……", flush=True)
    graph = ox.project_graph(
        ox.graph_from_point((LAT, LON), dist=SEARCH_RADIUS_M, network_type="walk")
    )
    crs = graph.graph["crs"]
    station = gpd.GeoSeries([Point(LON, LAT)], crs="EPSG:4326").to_crs(crs).iloc[0]
    nodes = list(graph.nodes)
    positions = np.array([[graph.nodes[n]["x"], graph.nodes[n]["y"]] for n in nodes])
    tree = cKDTree(positions)
    _, origin_idx = tree.query([station.x, station.y])
    origin = nodes[origin_idx]
    for _, _, edge in graph.edges(data=True):
        edge["travel_time"] = edge["length"] / WALK_SPEED_M_S
    durations, paths = nx.single_source_dijkstra(
        graph, origin, cutoff=30 * 60, weight="travel_time"
    )

    transit = ox.features_from_point((LAT, LON), TAGS, dist=SEARCH_RADIUS_M)
    transit = transit[transit.geometry.notna() & ~transit.geometry.is_empty].to_crs(crs).copy()
    transit["mode"] = transit.apply(transit_mode, axis=1)
    transit = transit[transit["mode"].notna()].copy()
    transit["point"] = transit.geometry.representative_point()
    transit = gpd.GeoDataFrame(transit.drop(columns="geometry"), geometry="point", crs=crs)
    transit["station_dist"] = transit.geometry.distance(station)
    transit = transit[transit.station_dist <= FOCUS_M].copy()
    if transit.empty:
        raise RuntimeError("车站附近没有可用的公交站或地铁出入口记录。")
    offset, closest = tree.query(np.array([(p.x, p.y) for p in transit.geometry]))
    transit["node"] = [nodes[i] for i in closest]
    transit["snap_m"] = offset
    transit["walk_min"] = [
        (durations.get(nodes[i], float("inf")) + d / WALK_SPEED_M_S) / 60
        for i, d in zip(closest, offset)
    ]
    transit["reachable"] = (transit.snap_m <= 150) & (transit.walk_min <= 30)
    transit["name_label"] = transit.apply(label, axis=1)
    for mode in COLORS:
        nearby = transit[transit["mode"] == mode]
        reached = nearby[nearby.reachable]
        print(f"{mode}: 研究图幅 {len(nearby)} 处，估算可达 {len(reached)} 处", flush=True)

    # 代表性路线：最近的地铁口，以及两个位置和站名不同的公交站。
    selected = []
    metro = transit[(transit["mode"] == "metro") & transit.reachable].sort_values("walk_min")
    if not metro.empty:
        selected.append(metro.iloc[0])
    buses = transit[(transit["mode"] == "bus") & transit.reachable].sort_values("walk_min")
    for _, stop in buses.iterrows():
        if all(stop["name_label"] != old["name_label"] and
               stop["point"].distance(old["point"]) > 170
               for old in selected if old["mode"] == "bus"):
            selected.append(stop)
        if sum(item["mode"] == "bus" for item in selected) == 2:
            break

    fig, ax = plt.subplots(figsize=(12, 12), dpi=180)
    fig.patch.set_facecolor("#F9FBFD")
    ax.set_facecolor("#F9FBFD")
    fig.subplots_adjust(left=0.035, right=0.965, top=0.865, bottom=0.175)
    ox.graph_to_gdfs(graph, nodes=False).geometry.plot(
        ax=ax, color="#DDE4E9", linewidth=0.70, zorder=1
    )
    for mode, style in COLORS.items():
        points = transit[transit["mode"] == mode]
        outside = points[~points.reachable]
        inside = points[points.reachable]
        if len(outside):
            outside.plot(ax=ax, color="#B6C1CB", markersize=33,
                         alpha=0.65, edgecolor="white", linewidth=0.6, zorder=3,
                         marker="^" if mode == "metro" else "o")
        if len(inside):
            inside.plot(ax=ax, color=style, markersize=72,
                        edgecolor="white", linewidth=0.9, zorder=5,
                        marker="^" if mode == "metro" else "o")

    for i, target in enumerate(selected):
        route = paths[target["node"]]
        if len(route) > 1:
            route_gdf = ox.routing.route_to_gdf(graph, route)
            route_gdf.geometry.plot(ax=ax, color=COLORS[target["mode"]],
                                    linewidth=3.3, alpha=0.82, zorder=6)
        # 最后一段路口至站点是直线连接示意，刻意用虚线与路网路线区分。
        node_pt = Point(graph.nodes[target["node"]]["x"], graph.nodes[target["node"]]["y"])
        ax.plot([node_pt.x, target["point"].x], [node_pt.y, target["point"].y],
                color=COLORS[target["mode"]], linestyle="--", linewidth=1.1, zorder=7)
        ax.annotate(str(i + 1), (target["point"].x, target["point"].y),
                    xytext=(7, 9), textcoords="offset points", fontsize=9,
                    color="white", weight="bold", zorder=9,
                    bbox=dict(boxstyle="circle,pad=0.25",
                              facecolor=COLORS[target["mode"]],
                              edgecolor="white", linewidth=0.8))

    ax.scatter(station.x, station.y, c="#233E59", marker="*", s=180,
               edgecolors="white", linewidth=1.2, zorder=10)
    ax.annotate("成都东站", (station.x, station.y), xytext=(8, 10),
                textcoords="offset points", fontsize=12, weight="bold",
                color="#233E59", zorder=11,
                bbox=dict(facecolor="#F9FBFD", edgecolor="none", alpha=0.85, pad=1))
    span = FOCUS_M * 1.09
    ax.set_xlim(station.x - span, station.x + span)
    ax.set_ylim(station.y - span, station.y + span)
    ax.set_aspect("equal")
    ax.axis("off")
    route_list = "代表性换乘路线\n" + "\n".join(
        f"{i + 1}  {target['name_label']}   {target['walk_min']:.1f} 分钟"
        for i, target in enumerate(selected)
    )
    ax.text(0.965, 0.96, route_list, transform=ax.transAxes, ha="right", va="top",
            fontsize=10, color="#213B52", linespacing=1.7, zorder=12,
            bbox=dict(boxstyle="round,pad=0.65", facecolor="#F9FBFD",
                      edgecolor="#DCE4EA", alpha=0.94))

    fig.text(0.065, 0.955, "成都东站 · 公交地铁换乘步行图",
             fontsize=23, weight="bold", color="#213B52", va="top")
    fig.text(0.066, 0.913, "从车站定位点沿步行路网到地铁出入口、公交站   /   车站周边约 1 公里",
             fontsize=10.5, color="#5D7181", va="top")
    handles = [
        Line2D([], [], marker="^", color=COLORS["metro"], linestyle="", markersize=9,
               label=f"地铁出入口 {((transit['mode'] == 'metro') & transit.reachable).sum()} 处（青绿）"),
        Line2D([], [], marker="o", color=COLORS["bus"], linestyle="", markersize=8,
               label=f"公交站 {((transit['mode'] == 'bus') & transit.reachable).sum()} 处（紫色）"),
    ]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.066, 0.124),
               frameon=False, ncol=2, fontsize=9.5, labelcolor="#213B52")
    fig.text(0.067, 0.098,
             "彩色路线为代表性站点的最短步行路；末端虚线为路口到站点的直线连接，并非核实的入口路线。",
             fontsize=8.5, color="#5D7181")
    fig.text(0.067, 0.074,
             "步速 4.8 km/h；从车站定位点而非真实出站口起算，不含站内步行、信号等待及候车。",
             fontsize=8.5, color="#5D7181")
    fig.text(0.067, 0.049, "站点与道路数据 © OpenStreetMap contributors  |  地图记录可能缺漏  |  计算：OSMnx / NetworkX",
             fontsize=8.1, color="#788B9A")
    output = ROOT / "chengdudong_transfer_walk.png"
    fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"已保存：{output}", flush=True)


if __name__ == "__main__":
    main()

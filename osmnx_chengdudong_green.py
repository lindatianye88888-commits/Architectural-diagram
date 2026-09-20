"""成都东站步行 15/30 分钟内，OpenStreetMap 公园、游园和城市广场的可达性示意。"""

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
import shapely
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.spatial import cKDTree
from shapely.geometry import Point

from osmnx_chengdudong_30min import (
    BAND_WIDTH_M, LAT, LON, ROOT, SEARCH_RADIUS_M,
    WALK_SPEED_M_S, reachable_lines,
)


TAGS = {
    "leisure": ["park", "garden", "playground"],
    "landuse": "recreation_ground",
    "place": "square",
}


def space_type(item):
    if item.get("place") == "square":
        return "square"
    if item.get("leisure") in {"park", "garden"}:
        return "green"
    if item.get("landuse") == "recreation_ground":
        return "green"
    # 幼儿游乐设施可能属于封闭小区；无公共准入证据时不归为公共空间。
    return None


def main():
    print("读取步行路网、公园游园和广场记录……", flush=True)
    graph = ox.project_graph(
        ox.graph_from_point((LAT, LON), dist=SEARCH_RADIUS_M, network_type="walk")
    )
    crs = graph.graph["crs"]
    station = gpd.GeoSeries([Point(LON, LAT)], crs="EPSG:4326").to_crs(crs).iloc[0]
    nodes = list(graph.nodes)
    positions = np.asarray([(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in nodes])
    _, idx = cKDTree(positions).query([station.x, station.y])
    for _, _, edge in graph.edges(data=True):
        edge["travel_time"] = edge["length"] / WALK_SPEED_M_S
    times = nx.single_source_dijkstra_path_length(
        graph, nodes[idx], cutoff=1800, weight="travel_time"
    )
    lines_15 = reachable_lines(graph, times, 900)
    lines_30 = reachable_lines(graph, times, 1800)
    roads_15 = gpd.GeoSeries([gpd.GeoSeries(lines_15, crs=crs).union_all()], crs=crs)
    roads_30 = gpd.GeoSeries([gpd.GeoSeries(lines_30, crs=crs).union_all()], crs=crs)

    spaces = ox.features_from_point((LAT, LON), TAGS, dist=SEARCH_RADIUS_M)
    spaces = spaces[spaces.geometry.notna() & ~spaces.geometry.is_empty].to_crs(crs).copy()
    spaces["kind"] = spaces.apply(space_type, axis=1)
    spaces = spaces[spaces.kind.notna()].copy()
    if spaces.empty:
        raise RuntimeError("研究区没有已标注的公园、游园和广场。")

    # 面状设施计算「最近可达路口到其边界」的估计时间，不用中心点代替入口。
    reached_nodes = list(times)
    reached_points = shapely.points(
        np.array([(graph.nodes[n]["x"], graph.nodes[n]["y"])
                  for n in reached_nodes])
    )
    reached_seconds = np.array([times[n] for n in reached_nodes])
    estimated_minutes = []
    for geom in spaces.geometry:
        d = shapely.distance(reached_points, geom)
        valid = d <= 200  # 距设施边界超过 200 m 的路口不视为就近接入
        estimated_minutes.append(
            float(np.min((reached_seconds[valid] + d[valid] / WALK_SPEED_M_S) / 60))
            if valid.any() else float("inf")
        )
    spaces["walk_min"] = estimated_minutes
    spaces["period"] = np.select(
        [spaces.walk_min <= 15, spaces.walk_min <= 30],
        ["15", "30"], default="outside"
    )
    green = spaces[spaces.kind == "green"]
    square = spaces[spaces.kind == "square"]
    for category, items in (("park_garden", green), ("square", square)):
        print(f"{category}: total={len(items)} in15={(items.period == '15').sum()} "
              f"in30={(items.period != 'outside').sum()}", flush=True)

    fig, ax = plt.subplots(figsize=(12, 12), dpi=180)
    fig.patch.set_facecolor("#F9FBFD")
    ax.set_facecolor("#F9FBFD")
    fig.subplots_adjust(left=0.035, right=0.965, top=0.86, bottom=0.20)
    ox.graph_to_gdfs(graph, nodes=False).geometry.plot(
        ax=ax, color="#DEE4E8", linewidth=0.46, zorder=1
    )
    roads_30.buffer(BAND_WIDTH_M).plot(
        ax=ax, facecolor="#D8E9F4", edgecolor="none", alpha=0.55, zorder=2
    )
    roads_15.buffer(BAND_WIDTH_M).plot(
        ax=ax, facecolor="#A9CAE1", edgecolor="none", alpha=0.48, zorder=3
    )
    roads_30.plot(ax=ax, color="#AAC2D1", linewidth=0.65, zorder=4)
    roads_15.plot(ax=ax, color="#668CA7", linewidth=0.70, zorder=5)

    area = spaces[spaces.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    colors = {"outside": "#DCE3DF", "30": "#80BC97", "15": "#277856"}
    for period in ("outside", "30", "15"):
        selected = area[(area.kind == "green") & (area.period == period)]
        if not selected.empty:
            selected.plot(ax=ax, facecolor=colors[period], edgecolor="#8CA49A",
                          linewidth=0.65, alpha=0.65 if period == "outside" else 0.85,
                          zorder=6 + (period == "15"))
    for _, place in spaces[spaces.kind == "square"].iterrows():
        p = place.geometry.representative_point()
        c = "#536BB5" if place.period != "outside" else "#AAB2BE"
        ax.scatter(p.x, p.y, marker="D", s=70, color=c, edgecolors="white",
                   linewidths=0.7, zorder=9)
    green_points = spaces[(spaces.kind == "green") & spaces.geometry.geom_type.eq("Point")]
    if not green_points.empty:
        for _, place in green_points.iterrows():
            ax.scatter(place.geometry.x, place.geometry.y, s=45,
                       color=colors[place.period], edgecolors="white", zorder=8)

    # 仅标注近邻且有名称的少数大型/较近绿地，避免与面状分布相互遮挡。
    named = green[(green.period != "outside") & green.get("name").notna()]
    named = named.sort_values("walk_min").head(3)
    for _, park in named.iterrows():
        position = park.geometry.representative_point()
        ax.annotate(str(park["name"])[:9], (position.x, position.y),
                    xytext=(6, 7), textcoords="offset points", fontsize=8.2,
                    color="#245E4F", zorder=10,
                    bbox=dict(facecolor="#F9FBFD", edgecolor="none", alpha=0.78, pad=1.0))
    ax.scatter(station.x, station.y, c="#223D59", s=140, marker="*",
               edgecolors="white", linewidth=1.15, zorder=11)
    ax.annotate("成都东站", (station.x, station.y), xytext=(8, 8),
                textcoords="offset points", fontsize=12, color="#223D59",
                weight="bold", zorder=12)
    span = SEARCH_RADIUS_M * 1.04
    ax.set_xlim(station.x - span, station.x + span)
    ax.set_ylim(station.y - span, station.y + span)
    ax.set_aspect("equal")
    ax.axis("off")

    fig.text(0.065, 0.955, "成都东站 · 绿地与公共空间可达图",
             fontsize=22, weight="bold", color="#213B52", va="top")
    fig.text(0.066, 0.913,
             f"OpenStreetMap 公园／游园 {len(green)} 处、广场 {len(square)} 处  /  步行 15 与 30 分钟",
             fontsize=10.5, color="#5D7181", va="top")
    handles = [
        Patch(facecolor=colors["15"], edgecolor="none",
              label=f"15 分钟内绿地  {(green.period == '15').sum()} 处"),
        Patch(facecolor=colors["30"], edgecolor="none",
              label=f"15–30 分钟绿地  {(green.period == '30').sum()} 处"),
        Patch(facecolor=colors["outside"], edgecolor="none", label="范围外已标注绿地"),
        Line2D([], [], marker="D",
               color="#536BB5" if (square.period != "outside").any() else "#AAB2BE",
               markersize=8, linestyle="",
               label=f"广场  {len(square)} 处（30 分钟内 {(square.period != 'outside').sum()} 处）"),
        Patch(facecolor="#A9CAE1", edgecolor="none", label="蓝色带：15/30 分钟道路示意"),
    ]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.066, 0.125),
               ncol=2, fontsize=9.1, frameon=False, labelcolor="#213B52",
               columnspacing=2.0)
    fig.text(0.067, 0.101, "绿地按边界到最近可达路口估算时间；图形可能延伸至步行圈外，非整个地块都可达。",
             fontsize=8.5, color="#5D7181")
    fig.text(0.067, 0.076, "未核实实际入口、围墙及开放性；未把无准入记录的游乐场与普通草坪直接当作公共绿地。",
             fontsize=8.5, color="#5D7181")
    fig.text(0.067, 0.051, "数据 © OpenStreetMap contributors  |  设施可能漏标  |  计算：OSMnx / NetworkX",
             fontsize=8.3, color="#788B9A")
    output = ROOT / "chengdudong_green_access.png"
    fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"已保存：{output}", flush=True)


if __name__ == "__main__":
    main()

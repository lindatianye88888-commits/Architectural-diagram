"""
成都东站 15 分钟生活圈 / 站点步行可达性分析（需联网 → dangerouslyDisableSandbox 运行）
方法：
  1) 抓取站点周边步行路网（graph_from_point，直连 Overpass，绕过被挡的 Nominatim）
  2) 以步行速度给路段赋通行时间，从站点做单源最短路径 → 每个路口的步行时间
  3) 取 <=15 分钟可达的路口，生成可达范围(reachable blob) + 可达路网
  4) 量化：可达面积 / 可达路口数及占比 / 可达路网长度 / 平均步行时间
"""
import os
import networkx as nx
import osmnx as ox
import geopandas as gpd
from shapely.geometry import MultiPoint
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans SC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

ox.settings.timeout = 600
ox.settings.log_console = False

# 成都东站（Chengdu East Railway Station）坐标
LAT, LON = 30.6308, 104.1411
WALK_MIN = 15
SPEED_M_S = 4800 / 3600.0  # 4.8 km/h 步行速度
THRESH_S = WALK_MIN * 60    # 900 s
STUDY_DIST = 1800           # 抓取范围(米)，略大于 15 分钟步行半径以得到完整边界

print("下载成都东站周边步行路网……")
G = ox.graph_from_point((LAT, LON), dist=STUDY_DIST, network_type="walk")

# 投影到 UTM(米)：最近点查找 / buffer / 面积均用真实距离，免装 scikit-learn
G = ox.project_graph(G)
station_utm = gpd.GeoSeries(gpd.points_from_xy([LON], [LAT]), crs=4326).to_crs(32648).iloc[0]

# 给每段路赋步行时间(秒)
for u, v, k, data in G.edges(keys=True, data=True):
    data["travel_time"] = data["length"] / SPEED_M_S

# 最近路口作为起点（投影坐标下手动求最近，免装 scipy）
sx, sy = station_utm.x, station_utm.y
orig = min(G.nodes, key=lambda n: (G.nodes[n]["x"] - sx) ** 2 + (G.nodes[n]["y"] - sy) ** 2)
print(f"起点路口: {orig}")

# 单源最短步行时间
lengths = nx.single_source_dijkstra_path_length(G, orig, weight="travel_time")
reach_nodes = {n for n, t in lengths.items() if t <= THRESH_S}

# ---- 指标 ----
all_nodes = set(G.nodes())
reach_intersections = len(reach_nodes)
total_intersections = len(all_nodes)
reach_ratio = reach_intersections / total_intersections * 100

G_sub = G.subgraph(reach_nodes)
reach_len_km = sum(d["length"] for u, v, k, d in G_sub.edges(keys=True, data=True)) / 1000.0
total_len_km = sum(d["length"] for u, v, k, d in G.edges(keys=True, data=True)) / 1000.0

# 可达范围 = 可达路段几何 buffer 成带状（network buffer，比路口点圆更贴合街道）
edges_sub = ox.graph_to_gdfs(G_sub, nodes=False)
band = edges_sub.geometry.union_all().buffer(35).simplify(12)
band_gdf = gpd.GeoDataFrame(geometry=[band], crs=G.graph["crs"])
reach_area_km2 = float(band_gdf.area.sum()) / 1e6

reach_times = [t for t in lengths.values() if t <= THRESH_S]
avg_time = sum(reach_times) / len(reach_times)

print(f"研究区路口: {total_intersections}  15分钟内可达: {reach_intersections} ({reach_ratio:.0f}%)")
print(f"研究区路网: {total_len_km:.1f} km  15分钟可达路网: {reach_len_km:.1f} km")
print(f"15分钟可达面积: {reach_area_km2:.2f} km^2")
print(f"可达路口平均步行时间: {avg_time/60:.1f} min")

# ---- 出图 ----
fig, ax = plt.subplots(figsize=(11, 11), dpi=200)
fig.patch.set_facecolor("#f4f1ea")
ax.set_facecolor("#f4f1ea")

# 底图：研究区全路网（更浅，突出可达范围）
ox.plot_graph(G, ax=ax, node_size=0, edge_color="#e2dbc9",
              edge_linewidth=0.35, bgcolor="#f4f1ea", show=False, close=False)

# 可达范围带状填充
band_gdf.plot(ax=ax, facecolor="#c9a36b", alpha=0.30,
              edgecolor="none", linewidth=0)

# 可达路网（强调色）
ox.plot_graph(G_sub, ax=ax, node_size=0, edge_color="#a8743f",
              edge_linewidth=0.9, bgcolor="#f4f1ea", show=False, close=False)

# 站点标记（投影坐标系下的坐标）
ax.scatter([station_utm.x], [station_utm.y], c="#8a3b2e", s=90, zorder=5,
           marker="*", edgecolors="white", linewidths=1.2)
ax.annotate("成都东站", (station_utm.x, station_utm.y), xytext=(6, 6),
            textcoords="offset points", fontsize=11, color="#8a3b2e",
            fontweight="bold")

ax.set_axis_off()
ax.set_title("成都东站 15 分钟步行生活圈 · 站点可达性分析", fontsize=16,
             color="#5c4631", fontweight="bold", pad=14)

legend_handles = [
    Line2D([0], [0], color="#a8743f", lw=1.0, label="15分钟内可达路网"),
    Line2D([0], [0], color="#e2dbc9", lw=1.0, label="研究区其余路网"),
    Line2D([0], [0], marker="*", color="#8a3b2e", lw=0, markersize=11,
           label="成都东站"),
]
ax.legend(handles=legend_handles, loc="lower left", frameon=False,
          fontsize=9, labelcolor="#5c4631")

metrics_text = (
    f"步行速度  4.8 km/h\n"
    f"可达面积  {reach_area_km2:.2f} km²\n"
    f"可达路口  {reach_intersections:,} / {total_intersections:,}（{reach_ratio:.0f}%）\n"
    f"可达路网  {reach_len_km:.0f} km（占 {reach_len_km/total_len_km*100:.0f}%）\n"
    f"平均步行时间  {avg_time/60:.1f} min"
)
ax.text(0.985, 0.985, metrics_text, transform=ax.transAxes,
        ha="right", va="top", fontsize=10, color="#5c4631", linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#faf8f3",
                  edgecolor="#d8d0c0", linewidth=0.8))

out_png = os.path.join(os.path.dirname(__file__), "chengdudong_15min.png")
plt.savefig(out_png, dpi=200, bbox_inches="tight", facecolor="#f4f1ea")
print(f"已保存: {out_png}")
print("完成。")

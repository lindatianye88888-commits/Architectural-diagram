"""
成华区路网分析图（需联网 → dangerouslyDisableSandbox 运行）
改用 graph_from_bbox 直接按经纬度范围抓 Overpass 数据，绕开被代理挡住的 Nominatim 地名解析。
- 成华区大致 bbox：104.03~104.185 E，30.58~30.735 N
- 按道路等级分层着色（低饱和大地色系）
- 输出指标：交叉口数 / 路网总长 / 平均连接度 / 路网密度
"""
import os
import osmnx as ox
import geopandas as gpd
from shapely.geometry import box
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans SC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

ox.settings.timeout = 600
ox.settings.log_console = True

NORTH, SOUTH, EAST, WEST = 30.735, 30.58, 104.185, 104.03

print("下载成华区 bbox 路网（Overpass）……")
G = ox.graph_from_bbox((WEST, SOUTH, EAST, NORTH), network_type="drive")

# ---- 基础指标 ----
n_nodes = G.number_of_nodes()
n_edges = G.number_of_edges()
degrees = [d for _, d in G.degree()]
avg_deg = sum(degrees) / len(degrees)

# bbox 面积（用于密度）
poly = gpd.GeoDataFrame(geometry=[box(WEST, SOUTH, EAST, NORTH)], crs=4326).to_crs(3857)
area_km2 = float(poly.area.sum()) / 1e6

edges = ox.graph_to_gdfs(G, nodes=False)
total_len_km = float(edges["length"].sum()) / 1000.0
density = (total_len_km * 1000) / area_km2

print(f"交叉口: {n_nodes}  路段: {n_edges}")
print(f"bbox 面积: {area_km2:.2f} km^2")
print(f"路网总长: {total_len_km:.1f} km")
print(f"平均连接度(节点度): {avg_deg:.2f}")
print(f"路网密度: {density:.0f} m/km^2")

# ---- 分级着色 ----
MAJOR = ["motorway", "motorway_link", "trunk", "trunk_link",
         "primary", "primary_link"]
MID = ["secondary", "secondary_link", "tertiary", "tertiary_link"]

def classify(hw):
    if isinstance(hw, list):
        hw = hw[0]
    if hw in MAJOR:
        return "major"
    if hw in MID:
        return "mid"
    return "minor"

color_map = {"major": "#5c4631", "mid": "#8a7257", "minor": "#b6a78f"}
width_map = {"major": 1.5, "mid": 0.9, "minor": 0.5}

edge_list = list(G.edges(keys=True))
colors, widths = [], []
for u, v, k in edge_list:
    hw = G[u][v][k].get("highway", "minor")
    cls = classify(hw)
    colors.append(color_map[cls])
    widths.append(width_map[cls])

# ---- 出图 ----
fig, ax = plt.subplots(figsize=(11, 11), dpi=200)
fig.patch.set_facecolor("#f4f1ea")
ax.set_facecolor("#f4f1ea")
ox.plot_graph(
    G, ax=ax,
    node_size=0,
    edge_color=colors,
    edge_linewidth=widths,
    bgcolor="#f4f1ea",
    show=False, close=False,
)
ax.set_axis_off()
legend_handles = [
    Line2D([0], [0], color=color_map["major"], lw=width_map["major"], label="主干/快速路"),
    Line2D([0], [0], color=color_map["mid"], lw=width_map["mid"], label="次干/支路干"),
    Line2D([0], [0], color=color_map["minor"], lw=width_map["minor"], label="街坊支路"),
]
ax.legend(handles=legend_handles, loc="lower left", frameon=False,
          fontsize=9, labelcolor="#5c4631")
ax.set_title("成都市成华区 机动车路网分析", fontsize=16, color="#5c4631",
             fontweight="bold", pad=14)

# 指标标注框（右上角）
metrics_text = (
    f"交叉口  {n_nodes:,} 个\n"
    f"路段    {n_edges:,} 条\n"
    f"路网总长  {total_len_km:,.0f} km\n"
    f"平均连接度  {avg_deg:.2f}\n"
    f"路网密度  {density:,.0f} m/km²"
)
ax.text(0.985, 0.985, metrics_text, transform=ax.transAxes,
        ha="right", va="top", fontsize=10, color="#5c4631",
        linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#faf8f3",
                  edgecolor="#d8d0c0", linewidth=0.8))

out_png = os.path.join(os.path.dirname(__file__), "chenghua_network.png")
plt.savefig(out_png, dpi=200, bbox_inches="tight", facecolor="#f4f1ea")
print(f"已保存: {out_png}")
print("完成。")

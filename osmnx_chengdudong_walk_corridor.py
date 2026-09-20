"""
成都东站 步行友好廊道图（需联网 → dangerouslyDisableSandbox 运行）
- 抓站点周边 walk 路网(2500m) → 投影 UTM 48N
- 高亮 L3 步行专用路/小径（pedestrian/footway/path/cycleway/steps/track），其余压灰底
- 量化：L3 段数/总长/占比，以及 L3 子图连通片数（碎片化程度）
- 中文字体：显式注册 msyh.ttc
"""
import os
import networkx as nx
import osmnx as ox
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.lines import Line2D

_fp = "C:/Windows/Fonts/msyh.ttc"
if os.path.exists(_fp):
    fm.fontManager.addfont(_fp)
    plt.rcParams["font.family"] = fm.FontProperties(fname=_fp).get_name()
plt.rcParams["axes.unicode_minus"] = False

ox.settings.timeout = 600
ox.settings.log_console = False

LAT, LON = 30.6308, 104.1411
STUDY_DIST = 2500

print("下载成都东站周边步行路网……")
G = ox.graph_from_point((LAT, LON), dist=STUDY_DIST, network_type="walk")
Gp = ox.project_graph(G, to_crs="EPSG:32648")

L3_TAGS = {"pedestrian", "footway", "path", "cycleway", "steps", "track"}


def hw_str(hw):
    if isinstance(hw, list):
        return hw[0]
    return hw


edge_list = list(Gp.edges(keys=True, data=True))
total_len = 0.0
l3_list, l3_len = [], 0.0
colors, widths = [], []
for u, v, k, d in edge_list:
    L = d.get("length", 0.0)
    total_len += L
    h = hw_str(d.get("highway", "footway"))
    if h in L3_TAGS:
        l3_list.append((u, v, k))
        l3_len += L
        colors.append("#2f6b48")        # 深绿：步行友好廊道
        widths.append(1.8)
    else:
        colors.append("#d2d8d2")        # 浅灰：其余步行路网
        widths.append(0.5)

# L3 连通片数（碎片化）
G3 = nx.Graph()
for u, v, k in l3_list:
    G3.add_edge(u, v)
n_comp = nx.number_connected_components(G3) if G3.number_of_edges() > 0 else 0
ratio = (l3_len / total_len * 100) if total_len else 0.0

print(f"步行路网总长: {total_len/1000:.1f} km")
print(f"L3 廊道: {len(l3_list)} 段 / {l3_len/1000:.1f} km / 占 {ratio:.1f}%")
print(f"L3 连通片数: {n_comp}")

# 站点 UTM
station = gpd.GeoSeries(gpd.points_from_xy([LON], [LAT]), crs=4326).to_crs(32648).iloc[0]
sx, sy = station.x, station.y

# ---- 出图 ----
fig, ax = plt.subplots(figsize=(11, 11), dpi=200)
fig.patch.set_facecolor("#eef1ec")
ax.set_facecolor("#eef1ec")

ox.plot_graph(Gp, ax=ax, node_size=0, edge_color=colors, edge_linewidth=widths,
              bgcolor="#eef1ec", show=False, close=False)

ax.scatter([sx], [sy], c="#2f3d35", s=130, marker="*",
           edgecolors="white", linewidths=1.3, zorder=5)
ax.annotate("成都东站", (sx, sy), xytext=(8, 8), textcoords="offset points",
            fontsize=11, color="#2f3d35", fontweight="bold", zorder=6)

ax.set_axis_off()
ax.set_title("成都东站周边 步行友好廊道", fontsize=16, color="#37463c",
             fontweight="bold", pad=14)
fig.text(0.065, 0.915, "深绿 = 独立步行廊道（不与车行混行）  /  浅灰 = 其余步行路网",
         fontsize=11, color="#5f7264", va="top")

# 指标框
metrics_text = (
    f"研究半径  {STUDY_DIST} m\n"
    f"步行路网总长  {total_len/1000:.1f} km\n"
    f"步行廊道(L3)  {len(l3_list)} 段 / {l3_len/1000:.1f} km\n"
    f"占比  {ratio:.1f}%\n"
    f"廊道连通片数  {n_comp} 片"
)
ax.text(0.985, 0.985, metrics_text, transform=ax.transAxes,
        ha="right", va="top", fontsize=10, color="#37463c", linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#faf8f3",
                  edgecolor="#cdd6cd", linewidth=0.8))

legend_handles = [
    Line2D([0], [0], color="#2f6b48", lw=1.8, label="步行友好廊道（L3）"),
    Line2D([0], [0], color="#d2d8d2", lw=1.0, label="其余步行路网"),
    Line2D([0], [0], marker="*", color="#2f3d35", lw=0, markersize=12,
           label="成都东站"),
]
ax.legend(handles=legend_handles, loc="lower left", frameon=False,
          fontsize=9, labelcolor="#37463c")

out = os.path.join(os.path.dirname(__file__), "chengdudong_walk_corridor.png")
plt.savefig(out, dpi=200, bbox_inches="tight", facecolor="#eef1ec")
print("已保存:", out)
print("完成。")

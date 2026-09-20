"""
成华区 道路方向与密度分析图（需联网 → dangerouslyDisableSandbox 运行）
- bbox：104.03~104.185 E，30.58~30.735 N（机动车路网）
- 主图：路网按走向(bearing)用低饱和色相环着色；灰色深浅=网格内路段密度
- 角标：方向玫瑰图(polar histogram)，含主导走向
- 中文字体：显式注册 msyh.ttc（最稳）
"""
import os
import colorsys
import numpy as np
import osmnx as ox
import geopandas as gpd
from shapely.geometry import box
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors, font_manager as fm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# ---- 中文字体：显式注册 ----
_fp = "C:/Windows/Fonts/msyh.ttc"
if os.path.exists(_fp):
    fm.fontManager.addfont(_fp)
    plt.rcParams["font.family"] = fm.FontProperties(fname=_fp).get_name()
plt.rcParams["axes.unicode_minus"] = False

ox.settings.timeout = 600
ox.settings.log_console = False

NORTH, SOUTH, EAST, WEST = 30.735, 30.58, 104.185, 104.03

print("下载成华区 bbox 路网（Overpass）……")
G = ox.graph_from_bbox((WEST, SOUTH, EAST, NORTH), network_type="drive")
ox.bearing.add_edge_bearings(G)                       # 未投影图上算 bearing（0=北，顺时针对应）
Gp = ox.project_graph(G, to_crs="EPSG:32648")          # 投影到 UTM 48N（米），bearing 属性保留

# ---- 基础指标 ----
n_nodes = Gp.number_of_nodes()
n_edges = Gp.number_of_edges()
degrees = [d for _, d in Gp.degree()]
avg_deg = sum(degrees) / len(degrees)
edges = ox.graph_to_gdfs(Gp, nodes=False)
total_len_km = float(edges["length"].sum()) / 1000.0
poly = gpd.GeoDataFrame(geometry=[box(WEST, SOUTH, EAST, NORTH)], crs=4326).to_crs(3857)
area_km2 = float(poly.area.sum()) / 1e6
density = (total_len_km * 1000) / area_km2

# ---- 方向分箱着色（12 箱，每 15°一色，低饱和色相环）----
PAL = [mcolors.to_hex(colorsys.hsv_to_rgb(i / 12, 0.26, 0.60)) for i in range(12)]
MAJOR = ("motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link")
MID = ("secondary", "secondary_link", "tertiary", "tertiary_link")

def style(u, v, k):
    d = Gp[u][v][k]
    b = d.get("bearing", 0)
    bi = int(b // 15) % 12
    hw = d.get("highway", "minor")
    if isinstance(hw, list):
        hw = hw[0]
    if hw in MAJOR:
        w = 1.4
    elif hw in MID:
        w = 0.85
    else:
        w = 0.45
    return PAL[bi], w

edge_list = list(Gp.edges(keys=True))
ecol, ew = [], []
for u, v, k in edge_list:
    c, w = style(u, v, k)
    ecol.append(c)
    ew.append(w)

# ---- 密度网格（基于边中点累加到网格，weight=长度）----
xs, ys, wl = [], [], []
for geom, L in zip(edges["geometry"], edges["length"]):
    p = geom.centroid
    xs.append(p.x); ys.append(p.y); wl.append(L)
xs = np.array(xs); ys = np.array(ys); wl = np.array(wl)
bins = 48
hist, xedges, yedges = np.histogram2d(xs, ys, bins=bins, weights=wl)

# ---- 出图 ----
fig, ax = plt.subplots(figsize=(12, 11), dpi=200)
fig.patch.set_facecolor("#eef1ec")
ax.set_facecolor("#eef1ec")

# 密度底（浅灰，不抢色）
mesh = ax.pcolormesh(xedges, yedges, hist.T, cmap="Greys", alpha=0.40, shading="flat")
# 路网按方向着色（叠加在上）
ox.plot_graph(Gp, ax=ax, node_size=0, edge_color=ecol, edge_linewidth=ew,
              bgcolor="#eef1ec", show=False, close=False)
ax.set_axis_off()
ax.set_title("成都市成华区 道路方向与密度分析", fontsize=16, color="#37463c",
             fontweight="bold", pad=14)
fig.text(0.065, 0.915, "路网按走向着色（色相=方向）  /  灰色深浅=网格内路段密度",
         fontsize=11, color="#5f7264", va="top")

# ---- 方向玫瑰图（右下角 inset）----
inset = fig.add_axes([0.70, 0.07, 0.27, 0.27], polar=True)
bearings = np.array([Gp[u][v][k].get("bearing", 0) for u, v, k in edge_list])
blen = np.array([Gp[u][v][k]["length"] for u, v, k in edge_list])
bi_all = np.concatenate([bearings, bearings + 180.0])      # 无向：镜像到后半圈
wi_all = np.concatenate([blen, blen])
nb = 36
theta = np.linspace(0, 2 * np.pi, nb, endpoint=False)
counts, _ = np.histogram(bi_all, bins=nb, range=(0, 360), weights=wi_all)
bw = 2 * np.pi / nb
bar_cols = [mcolors.to_hex(colorsys.hsv_to_rgb((i * 10) / 360, 0.26, 0.60)) for i in range(nb)]
inset.bar(theta, counts, width=bw, bottom=0, color=bar_cols,
          edgecolor="white", linewidth=0.3)
inset.set_theta_zero_location("N")
inset.set_theta_direction(-1)
inset.set_xticks(np.radians([0, 45, 90, 135, 180, 225, 270, 315]))
inset.set_xticklabels(["北", "东北", "东", "东南", "南", "西南", "西", "西北"],
                      fontsize=8, color="#37463c")
inset.tick_params(axis="y", labelsize=0)
inset.set_title("道路走向分布", fontsize=10, color="#37463c", pad=10)

# 主导走向
dom_deg = int(np.argmax(counts)) * 10
_compass = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
dom_txt = f"主导走向：{_compass[round(dom_deg / 45) % 8]}向（{dom_deg}°）"

# ---- 指标框 ----
metrics_text = (
    f"交叉口  {n_nodes:,} 个\n"
    f"路段  {n_edges:,} 条\n"
    f"路网总长  {total_len_km:,.0f} km\n"
    f"平均连接度  {avg_deg:.2f}\n"
    f"路网密度  {density:,.0f} m/km²\n"
    f"{dom_txt}"
)
ax.text(0.985, 0.985, metrics_text, transform=ax.transAxes,
        ha="right", va="top", fontsize=10, color="#37463c", linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#faf8f3",
                  edgecolor="#cdd6cd", linewidth=0.8))

# ---- 方向色例 ----
legend_elements = [Patch(facecolor=PAL[i], label=f"{i * 15}–{(i + 1) * 15}°")
                   for i in range(12)]
ax.legend(handles=legend_elements, loc="lower left", frameon=False,
          fontsize=7.5, ncol=2, labelcolor="#37463c",
          title="道路走向", title_fontsize=9)

# ---- 密度 colorbar ----
cb = fig.colorbar(mesh, ax=ax, fraction=0.025, pad=0.02, aspect=42,
                  orientation="horizontal")
cb.set_label("网格内道路总长（km）", fontsize=9, color="#5f7264")
cb.ax.tick_params(labelsize=7, colors="#5f7264")

out = os.path.join(os.path.dirname(__file__), "chenghua_orientation.png")
plt.savefig(out, dpi=200, bbox_inches="tight", facecolor="#eef1ec")
print("已保存:", out)
print("主导走向:", dom_txt)
print("完成。")

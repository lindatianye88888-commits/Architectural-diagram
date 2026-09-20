"""
成都东站 路口/节点密度热力图（需联网 → dangerouslyDisableSandbox 运行）
- 抓站点周边 walk 路网(2000m) → 投影 UTM 48N
- 节点坐标做网格计数 → numpy 一维高斯卷积做 2D 平滑（零依赖）
- 绿系渐变热力底 + 浅色路网 + 站点星标 + 密度峰值标记
- 中文字体：显式注册 msyh.ttc
"""
import os
import numpy as np
import osmnx as ox
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

_fp = "C:/Windows/Fonts/msyh.ttc"
if os.path.exists(_fp):
    fm.fontManager.addfont(_fp)
    plt.rcParams["font.family"] = fm.FontProperties(fname=_fp).get_name()
plt.rcParams["axes.unicode_minus"] = False

ox.settings.timeout = 600
ox.settings.log_console = False

LAT, LON = 30.6308, 104.1411
STUDY_DIST = 2000

print("下载成都东站周边步行路网……")
G = ox.graph_from_point((LAT, LON), dist=STUDY_DIST, network_type="walk")
Gp = ox.project_graph(G, to_crs="EPSG:32648")

# 节点（路口）UTM 坐标
xs = np.array([d["x"] for _, d in Gp.nodes(data=True)])
ys = np.array([d["y"] for _, d in Gp.nodes(data=True)])
n_nodes = len(xs)

# 站点 UTM 坐标
station = gpd.GeoSeries(gpd.points_from_xy([LON], [LAT]), crs=4326).to_crs(32648).iloc[0]
sx, sy = station.x, station.y

# 网格计数
bins = 120
hist, xedges, yedges = np.histogram2d(xs, ys, bins=bins)


# 纯 numpy 可分离高斯平滑
def gaussian_smooth(mat, sigma):
    ks = int(4 * sigma) + 1
    xx = np.arange(-ks, ks + 1)
    k = np.exp(-(xx ** 2) / (2 * sigma ** 2))
    k /= k.sum()
    m = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), axis=1, arr=mat)
    m = np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), axis=0, arr=m)
    return m


smooth = gaussian_smooth(hist, sigma=1.0)
peak_idx = np.unravel_index(np.argmax(smooth), smooth.shape)
peak_x = 0.5 * (xedges[peak_idx[1]] + xedges[peak_idx[1] + 1])
peak_y = 0.5 * (yedges[peak_idx[0]] + yedges[peak_idx[0] + 1])
peak_val = smooth[peak_idx]
cell_area_m2 = ((xedges[1] - xedges[0]) * (yedges[1] - yedges[0]))
peak_density = peak_val / (cell_area_m2 / 1e6)  # 个/km²

print(f"路口数: {n_nodes}")
print(f"密度峰值: {peak_val:.1f} 个/格  ≈ {peak_density:,.0f} 个/km²  @({peak_x:.0f},{peak_y:.0f})")

# ---- 出图 ----
fig, ax = plt.subplots(figsize=(11, 11), dpi=200)
fig.patch.set_facecolor("#eef1ec")
ax.set_facecolor("#eef1ec")

# 热力底（绿系）
mesh = ax.pcolormesh(xedges, yedges, smooth.T, cmap="YlGn", shading="flat", alpha=0.85)
# 路网浅色叠加（结构清晰）
ox.plot_graph(Gp, ax=ax, node_size=0, edge_color="#c4cdc6",
              edge_linewidth=0.4, bgcolor="#eef1ec", show=False, close=False)
# 站点
ax.scatter([sx], [sy], c="#2f3d35", s=130, marker="*",
           edgecolors="white", linewidths=1.3, zorder=5)
ax.annotate("成都东站", (sx, sy), xytext=(8, 8), textcoords="offset points",
            fontsize=11, color="#2f3d35", fontweight="bold", zorder=6)
# 密度峰值
ax.scatter([peak_x], [peak_y], c="#9c2b2b", s=55, marker="o",
           edgecolors="white", linewidths=1.0, zorder=5)
ax.annotate("密度峰值", (peak_x, peak_y), xytext=(8, -14), textcoords="offset points",
            fontsize=9, color="#9c2b2b", zorder=6)

ax.set_axis_off()
ax.set_title("成都东站周边 路口（节点）密度热力", fontsize=16, color="#37463c",
             fontweight="bold", pad=14)
fig.text(0.065, 0.915, "绿系深浅 = 路口密度（高斯平滑）  /  浅灰线 = 步行路网",
         fontsize=11, color="#5f7264", va="top")

# 指标框
metrics_text = (
    f"研究半径  {STUDY_DIST} m\n"
    f"路口总数  {n_nodes:,} 个\n"
    f"网格峰值密度  {peak_val:.1f} 个/格\n"
    f"≈ {peak_density:,.0f} 个/km²\n"
    f"路网类型  walk（步行）"
)
ax.text(0.985, 0.985, metrics_text, transform=ax.transAxes,
        ha="right", va="top", fontsize=10, color="#37463c", linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.6", facecolor="#faf8f3",
                  edgecolor="#cdd6cd", linewidth=0.8))

# colorbar
cb = fig.colorbar(mesh, ax=ax, fraction=0.026, pad=0.02, aspect=42,
                  orientation="horizontal")
cb.set_label("路口密度（个 / 网格）", fontsize=9, color="#5f7264")
cb.ax.tick_params(labelsize=7, colors="#5f7264")

# 图例
legend_handles = [
    Line2D([0], [0], marker="*", color="#2f3d35", lw=0, markersize=12, label="成都东站"),
    Line2D([0], [0], marker="o", color="#9c2b2b", lw=0, markersize=8,
           markerfacecolor="#9c2b2b", markeredgecolor="white", label="密度峰值"),
]
ax.legend(handles=legend_handles, loc="lower left", frameon=False,
          fontsize=9, labelcolor="#37463c")

out = os.path.join(os.path.dirname(__file__), "chengdudong_node_density.png")
plt.savefig(out, dpi=200, bbox_inches="tight", facecolor="#eef1ec")
print("已保存:", out)
print("完成。")

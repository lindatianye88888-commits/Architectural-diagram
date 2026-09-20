"""宽窄巷子：传统街巷与二期项目区位数据图。

运行：python osmnx_kuanzhai_history_planning.py
输出：kuanzhai_history_planning.png

重要口径：历史事件来自成都市文旅部门，二期规模来自成都商报，
地图几何来自当期 OpenStreetMap；OSM 二期面状要素不是法定规划红线。
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import osmnx as ox
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Patch


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "kuanzhai_history_planning.png"
CENTER = (30.66665, 104.05015)
LANES = ("宽巷子", "窄巷子", "井巷子")
PROJECT = "宽窄巷子二期"

HISTORY_SOURCE = "https://cd3000y.cccic.org.cn/views/3DMuseum/OldStreet.aspx"
PROJECT_SOURCE = (
    "https://news.chengdu.cn/2026/0617/6a31f160cfd50212c36dcfd6.shtml"
)

BG = "#f8f6f1"
INK = "#27333a"
MUTED = "#68737a"
OLD = "#ae5b37"
NEW = "#187985"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans SC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

ox.settings.use_cache = True
ox.settings.cache_folder = str(ROOT / "cache")
ox.settings.timeout = 300


def get_layers():
    roads = ox.graph_from_point(CENTER, dist=850, network_type="walk")
    road_edges = ox.graph_to_gdfs(ox.project_graph(roads), nodes=False)
    named = ox.features_from_point(
        CENTER, dist=850, tags={"name": [*LANES, PROJECT]}
    )
    named = ox.projection.project_gdf(named)
    lane_lines = named[
        named["name"].isin(LANES) & named.geometry.geom_type.isin(["LineString", "MultiLineString"])
    ].copy()
    project = named[(named["name"] == PROJECT) & named.geometry.geom_type.isin(
        ["Polygon", "MultiPolygon"]
    )].copy()
    if lane_lines.empty or project.empty or set(lane_lines["name"]) != set(LANES):
        raise RuntimeError("OSM 的传统三巷或二期面状要素缺失，不能绘制此图。")

    context = ox.features_from_point(
        CENTER, dist=750, tags={"building": True, "leisure": ["park", "garden"]}
    )
    context = ox.projection.project_gdf(context)
    buildings = context[
        context.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        & context["building"].notna()
    ].copy()
    parks = context[
        context.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        & context["leisure"].isin(["park", "garden"])
    ].copy()
    return road_edges, buildings, parks, lane_lines, project


def main():
    roads, buildings, parks, lanes, project = get_layers()
    bounds = gpd.GeoSeries(
        list(lanes.geometry) + list(project.geometry), crs=lanes.crs
    ).total_bounds
    minx, miny, maxx, maxy = bounds
    x0, x1 = minx - 145, maxx + 145
    y0, y1 = miny - 150, maxy + 155

    project_area_ha = project.geometry.area.sum() / 10000
    official_area_ha = 23 * (10000 / 15) / 10000  # 1 亩 = 666.67 m²
    lane_lengths = lanes.groupby("name").geometry.apply(lambda a: a.length.sum())
    total_lane_km = lane_lengths.sum() / 1000
    print(
        f"三巷 OSM 中心线：{total_lane_km:.3f} km；"
        f"公开报道二期占地：{official_area_ha:.2f} ha；"
        f"OSM 二期要素：{project_area_ha:.2f} ha；"
        f"面积差：{project_area_ha - official_area_ha:.2f} ha",
        flush=True,
    )

    fig = plt.figure(figsize=(15.2, 9.25), dpi=190, facecolor=BG)
    grid = fig.add_gridspec(
        nrows=2, ncols=2, width_ratios=[1.33, 1], height_ratios=[1, 1],
        left=0.055, right=0.955, bottom=0.17, top=0.795,
        wspace=0.075, hspace=0.11,
    )
    ax = fig.add_subplot(grid[:, 0], facecolor="#f1f0ec")
    timeline = fig.add_subplot(grid[0, 1], facecolor=BG)
    facts = fig.add_subplot(grid[1, 1], facecolor=BG)

    fig.text(0.055, 0.934, "宽窄巷子｜传统街巷与二期发展", fontsize=26,
             fontweight="bold", color=INK)
    fig.text(0.055, 0.880, "历史格局 · 当前街巷线位 · 已公开的建设规模",
             fontsize=13, color=MUTED)
    fig.text(0.055, 0.830, "01  空间区位 / OpenStreetMap 现状标绘",
             fontsize=12, fontweight="bold", color=INK)

    if not parks.empty:
        parks.plot(ax=ax, color="#dce6d5", linewidth=0, zorder=1)
    if not buildings.empty:
        buildings.plot(ax=ax, color="#dbdcd8", edgecolor="#f1f0ec",
                       linewidth=0.35, zorder=2)
    roads.plot(ax=ax, color="#ffffff", linewidth=1.25, zorder=3)
    roads.plot(ax=ax, color="#c1c5c3", linewidth=0.43, zorder=4)

    # OSM 众包轮廓只作位置示意；不得作为项目批复边界使用。
    project.plot(ax=ax, color=NEW, alpha=0.22, linewidth=0, zorder=5)
    project.boundary.plot(ax=ax, color=NEW, linewidth=2.0,
                          linestyle=(0, (5, 3)), zorder=6)
    lanes.plot(ax=ax, color="#fff4e5", linewidth=7.5, zorder=7)
    lanes.plot(ax=ax, color=OLD, linewidth=3.8, zorder=8)

    # 东西向的街巷在图上略有倾斜，名称沿巷道中段错开排布。
    for name, offset in (("宽巷子", (20, 14)), ("窄巷子", (18, -25)),
                         ("井巷子", (2, -27))):
        geometry = lanes[lanes["name"] == name].geometry.iloc[0]
        mid = geometry.interpolate(0.46, normalized=True)
        ax.annotate(
            name, (mid.x, mid.y), xytext=offset, textcoords="offset points",
            ha="center", va="center", fontsize=12, fontweight="bold", color=OLD,
            bbox=dict(boxstyle="round,pad=0.20", fc=BG, ec="none", alpha=0.95),
            zorder=10,
        )

    centre = project.geometry.union_all().representative_point()
    ax.annotate(
        "二期区位\nOSM 位置示意", (centre.x, centre.y),
        ha="center", va="center", fontsize=11, linespacing=1.5,
        color="#115e69", fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.32", fc=BG, ec=NEW, lw=1.0, alpha=0.96),
        zorder=12,
    )

    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    ax.annotate("N", (0.94, 0.91), xycoords="axes fraction",
                ha="center", va="center", fontsize=13, color=INK, fontweight="bold")
    ax.annotate("↑", (0.94, 0.86), xycoords="axes fraction",
                ha="center", va="center", fontsize=22, color=INK)
    ax.plot([x0 + 28, x0 + 128], [y0 + 34, y0 + 34], color=INK, lw=2.6)
    ax.text(x0 + 78, y0 + 44, "100 m", ha="center", fontsize=9, color=INK)
    ax.legend(
        handles=[
            Line2D([0], [0], color=OLD, lw=4, label="传统三巷（当前 OSM 线位）"),
            Patch(facecolor=NEW, edgecolor=NEW, alpha=0.32,
                  label="二期 OSM 面状要素（非批复红线）"),
            Patch(facecolor="#dce6d5", label="OSM 公园/绿地"),
        ], loc="upper left", fontsize=9, frameon=True,
        facecolor=BG, edgecolor="#deded7", framealpha=0.97,
    )

    timeline.axis("off")
    timeline.set_xlim(0, 1)
    timeline.set_ylim(0, 1)
    timeline.text(0, 0.96, "02  保护与建设时间轴", fontsize=12,
                  fontweight="bold", color=INK)
    timeline.plot([0.065, 0.065], [0.16, 0.78], color="#d7d2c8", lw=2)
    marks = [
        (0.75, "20世纪80年代", "列入《成都历史文化名城保护规划》", OLD),
        (0.48, "2008年6月", "宽窄巷子保护性改造完成", OLD),
        (0.21, "2026年6月", "二期进入收尾阶段、启动预招商", NEW),
    ]
    for y, year, description, color in marks:
        timeline.add_patch(Circle((0.065, y), 0.014, color=color))
        timeline.text(0.12, y + 0.027, year, fontsize=16, color=color,
                      fontweight="bold", va="center")
        timeline.text(0.12, y - 0.037, description, fontsize=10.5,
                      color=INK, va="center")

    facts.axis("off")
    facts.set_xlim(0, 1)
    facts.set_ylim(0, 1)
    facts.text(0, 0.96, "03  可核验的规模数据", fontsize=12,
               fontweight="bold", color=INK)
    facts.text(0.025, 0.70, "3 条", fontsize=29, fontweight="bold", color=OLD)
    facts.text(0.29, 0.72, "传统巷道", fontsize=12, color=INK)
    facts.text(0.29, 0.61, f"现状 OSM 标绘中心线合计 {total_lane_km:.2f} km",
               fontsize=10, color=MUTED)
    facts.plot([0.01, 0.98], [0.55, 0.55], lw=0.75, color="#d9d6d0")
    facts.text(0.025, 0.36, "23 亩", fontsize=28, fontweight="bold", color=NEW)
    facts.text(0.36, 0.40, "二期公开报道占地", fontsize=11, color=INK)
    facts.text(0.36, 0.28, "约 2.3 万 m² 规划建筑面积", fontsize=10, color=MUTED)
    facts.text(0.025, 0.09,
               f"数据核验：报道占地约 {official_area_ha:.2f} ha；OSM 面状标绘约 {project_area_ha:.2f} ha。",
               fontsize=9.4, color="#9a553c")

    fig.text(0.055, 0.107,
             "读图提示：三巷采用当前地图线位表达历史格局，不是历史年份的测绘复原；二期轮廓仅指示区位。",
             fontsize=10.0, color=INK)
    fig.text(0.055, 0.075,
             "公开报道占地与 OSM 标绘面积不一致；未取得批复红线，不能据此计算项目法定用地或规划前后可达性增量。",
             fontsize=9.5, color="#9a553c")
    fig.text(0.055, 0.038,
             "来源：成都市文化广电旅游局历史文化街区资料；成都商报（2026-06-17）；© OpenStreetMap contributors。",
             fontsize=8.8, color=MUTED)
    fig.savefig(OUT, dpi=190, facecolor=BG)
    plt.close(fig)
    print(f"已生成：{OUT}", flush=True)
    print(f"历史出处：{HISTORY_SOURCE}", flush=True)
    print(f"二期出处：{PROJECT_SOURCE}", flush=True)


if __name__ == "__main__":
    main()

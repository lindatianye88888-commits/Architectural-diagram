"""成华区机动车道路密度网格 + 长度加权道路走向玫瑰图。

运行：python osmnx_chenghua_orientation_density.py
区界采用 OpenStreetMap 关系 4734807；不是旧图中的近似矩形。
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
from matplotlib import cm, colors
from shapely.geometry import box


ROOT = Path(__file__).resolve().parent
DISTRICT_RELATION = "R4734807"
GRID_M = 750
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans SC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
ox.settings.use_cache = True
ox.settings.cache_folder = str(ROOT / "cache")
ox.settings.timeout = 600


def make_grid(boundary, crs):
    minx, miny, maxx, maxy = boundary.bounds
    eastings = np.arange(np.floor(minx / GRID_M) * GRID_M, maxx, GRID_M)
    northings = np.arange(np.floor(miny / GRID_M) * GRID_M, maxy, GRID_M)
    polygons = []
    for x in eastings:
        for y in northings:
            piece = box(x, y, x + GRID_M, y + GRID_M).intersection(boundary)
            if not piece.is_empty and piece.area > 100:
                polygons.append(piece)
    grid = gpd.GeoDataFrame(geometry=polygons, crs=crs)
    grid["cell_id"] = np.arange(len(grid))
    grid["area_km2"] = grid.area / 1e6
    return grid


def axial_orientations(geometries):
    """按真实折线每一小段的投影长度计权，角度 0°=南北、90°=东西。"""
    bearings, lengths = [], []
    for geom in geometries:
        for segment in (geom.geoms if geom.geom_type == "MultiLineString" else [geom]):
            if segment.geom_type != "LineString":
                continue
            coords = np.asarray(segment.coords)
            if len(coords) < 2:
                continue
            differences = np.diff(coords, axis=0)
            distances = np.hypot(differences[:, 0], differences[:, 1])
            good = distances > 0.01
            bearings.extend((np.degrees(np.arctan2(
                differences[good, 0], differences[good, 1])) % 180).tolist())
            lengths.extend(distances[good].tolist())
    return np.asarray(bearings), np.asarray(lengths)


def main():
    print("读取成华区行政边界（OSM relation 4734807）……", flush=True)
    boundary_wgs84 = ox.geocode_to_gdf(DISTRICT_RELATION, by_osmid=True).geometry.iloc[0]
    if not boundary_wgs84.is_valid or boundary_wgs84.area <= 0:
        raise RuntimeError("成华区行政边界几何无效，不能继续计算。")
    print("读取区界内机动车道路……", flush=True)
    graph = ox.graph_from_polygon(
        boundary_wgs84, network_type="drive", retain_all=True, truncate_by_edge=True
    )
    graph = ox.project_graph(graph)
    crs = graph.graph["crs"]
    boundary = gpd.GeoSeries([boundary_wgs84], crs="EPSG:4326").to_crs(crs).iloc[0]

    # 将相反方向的双向边归并为一条道路中心线；不同的平行车行道仍分别计长。
    street_graph = ox.convert.to_undirected(graph)
    roads = ox.graph_to_gdfs(street_graph, nodes=False)[["geometry"]].reset_index(drop=True)
    roads = gpd.clip(roads, boundary, keep_geom_type=True)
    roads = roads[~roads.geometry.is_empty].copy()
    if roads.empty:
        raise RuntimeError("区界内没有可统计的道路。")

    boundary_area_km2 = boundary.area / 1e6
    total_street_km = roads.length.sum() / 1000
    mean_density = total_street_km / boundary_area_km2
    print(f"区面积 {boundary_area_km2:.1f} km2；车行道路 {total_street_km:.1f} km；平均密度 {mean_density:.2f} km/km2", flush=True)

    grid = make_grid(boundary, crs)
    # 先借助空间索引筛选，再裁剪路段到网格，边界格子按格子位于区内的实际面积计密度。
    road_parts = gpd.overlay(roads, grid[["cell_id", "geometry"]],
                             how="intersection", keep_geom_type=True)
    cell_km = (road_parts.assign(length_km=road_parts.length / 1000)
               .groupby("cell_id")["length_km"].sum())
    grid["density"] = grid["cell_id"].map(cell_km).fillna(0) / grid["area_km2"]
    valid_cells = grid[grid.area_km2 >= GRID_M ** 2 / 1e6 * 0.1]
    vmax = max(1, np.ceil(np.percentile(valid_cells.density, 98)))
    print(f"750 m 网格 {len(grid)} 个；密度分布 5%-95%={np.percentile(valid_cells.density,[5,95])}", flush=True)

    bearings, lengths = axial_orientations(roads.geometry)
    distribution, _ = np.histogram(
        bearings, bins=np.arange(0, 181, 15), weights=lengths
    )
    shares = distribution / distribution.sum() * 100
    dominant = np.argmax(shares) * 15 + 7.5
    if 22.5 <= dominant < 67.5:
        dominant_text = "东北—西南"
    elif 67.5 <= dominant < 112.5:
        dominant_text = "东西"
    elif 112.5 <= dominant < 157.5:
        dominant_text = "西北—东南"
    else:
        dominant_text = "南北"
    print(f"主导走向 {dominant_text}；方向轴 {dominant:.1f} 度", flush=True)

    fig = plt.figure(figsize=(16, 10), dpi=180, facecolor="#F8FBFD")
    ax_map = fig.add_axes([0.035, 0.155, 0.65, 0.705])
    ax_map.set_facecolor("#F8FBFD")
    cmap = "YlGnBu"
    grid.plot(ax=ax_map, column="density", cmap=cmap,
              vmin=0, vmax=vmax, edgecolor="white", linewidth=0.18, zorder=1)
    roads.plot(ax=ax_map, color="#315169", linewidth=0.19,
               alpha=0.32, zorder=2)
    gpd.GeoSeries([boundary], crs=crs).boundary.plot(
        ax=ax_map, color="#284A60", linewidth=1.15, zorder=3
    )
    ax_map.set_aspect("equal")
    ax_map.set_axis_off()
    bounds = boundary.bounds
    padding = 1000
    ax_map.set_xlim(bounds[0] - padding, bounds[2] + padding)
    ax_map.set_ylim(bounds[1] - padding, bounds[3] + padding)
    ax_map.annotate("N", xy=(0.93, 0.86), xytext=(0.93, 0.80),
                    xycoords="axes fraction", textcoords="axes fraction",
                    arrowprops=dict(arrowstyle="-|>", color="#284A60", lw=1.8),
                    ha="center", va="bottom", fontsize=13, weight="bold", color="#284A60")
    scalex, scaley = bounds[0] + 1700, bounds[1] + 1500
    ax_map.plot([scalex, scalex + 2000], [scaley, scaley],
                color="#284A60", lw=2.2, solid_capstyle="butt", zorder=6)
    ax_map.text(scalex + 1000, scaley + 130, "2 km", ha="center",
                fontsize=10, color="#284A60", zorder=6)

    ax_rose = fig.add_axes([0.745, 0.455, 0.225, 0.32], projection="polar")
    ax_rose.set_facecolor("#F8FBFD")
    rose_angles = np.deg2rad(np.arange(0, 360, 15) + 7.5)
    rose_shares = np.tile(shares, 2)
    rose_colors = plt.colormaps["PuBuGn"](0.33 + 0.57 * rose_shares / max(rose_shares))
    ax_rose.bar(rose_angles, rose_shares, width=np.deg2rad(14),
                color=rose_colors, edgecolor="#F8FBFD", linewidth=0.8, alpha=0.96)
    ax_rose.set_theta_zero_location("N")
    ax_rose.set_theta_direction(-1)
    ax_rose.set_xticks(np.deg2rad(np.arange(0, 360, 45)))
    ax_rose.set_xticklabels(["北", "东北", "东", "东南", "南", "西南", "西", "西北"],
                            fontsize=9, color="#284A60")
    ax_rose.set_yticks([])
    ax_rose.spines["polar"].set_color("#CBD9E2")
    ax_rose.grid(color="#DAE3E8", alpha=0.75)
    fig.text(0.741, 0.854, "道路方向", fontsize=17, weight="bold", color="#213B52")
    fig.text(0.742, 0.820, "每 15° 分组 · 道路长度加权 · 双向对称", fontsize=9, color="#5D7181")

    fig.text(0.742, 0.40, f"区界面积    {boundary_area_km2:.1f} km²",
             fontsize=12, color="#213B52")
    fig.text(0.742, 0.35, f"车行道路    {total_street_km:,.0f} km",
             fontsize=12, color="#213B52")
    fig.text(0.742, 0.30, f"平均密度    {mean_density:.1f} km/km²",
             fontsize=12, color="#213B52")
    fig.text(0.742, 0.25, f"主导走向    {dominant_text}",
             fontsize=12, color="#213B52")

    cax = fig.add_axes([0.143, 0.105, 0.42, 0.020])
    norm = colors.Normalize(vmin=0, vmax=vmax)
    cb = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap),
                      cax=cax, orientation="horizontal")
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=9, colors="#3E6175", length=2)
    fig.text(0.047, 0.107, "道路密度", fontsize=10, color="#284A60")
    fig.text(0.575, 0.107, "km/km²", fontsize=9.5, color="#284A60")

    fig.text(0.05, 0.935, "成华区 · 道路方向与密度", fontsize=27,
             weight="bold", color="#213B52")
    fig.text(0.05, 0.890, "机动车道路中心线  /  750 米网格  /  OpenStreetMap 成华区界",
             fontsize=12, color="#5D7181")
    fig.text(0.05, 0.063,
             "密度=格内道路中心线长度÷格内区界面积；区界小碎格可能波动，色标上限按有效网格第98百分位截断。",
             fontsize=9, color="#5D7181")
    fig.text(0.05, 0.038,
             "数据 © OpenStreetMap contributors（区界 relation 4734807） · 不代表交通流量或实际通行速度",
             fontsize=9, color="#788B9A")
    output = ROOT / "chenghua_road_orientation_density.png"
    fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"已保存：{output}", flush=True)


if __name__ == "__main__":
    main()

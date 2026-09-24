"""Export the existing Chengdu East green-space analysis for the Baidu web map.

Run once while connected to OSM (or with matching OSMnx responses in cache/):
    python osmnx_chengdudong_baidu_green_data.py
The output is WGS84; Baidu JS API 4.0 converts WGS84 overlay coordinates.
"""

import json
from datetime import datetime, timezone

import geopandas as gpd
from shapely.geometry import mapping
from shapely.ops import linemerge

from osmnx_chengdudong_30min import LAT, LON, ROOT, WALK_SPEED_M_S
from osmnx_chengdudong_green import build_accessibility


OUTPUT = ROOT / "data" / "chengdudong_green_access_wgs84.json"


def to_wgs84(geometry, crs):
    return mapping(gpd.GeoSeries([geometry], crs=crs).to_crs("EPSG:4326").iloc[0])


def reachable_geometry(lines, crs):
    # Topological merge removes duplicate two-way road segments. Simplification
    # is for display only; travel-time calculations use the original graph.
    merged = gpd.GeoSeries(lines, crs=crs).union_all()
    if merged.geom_type == "MultiLineString":
        merged = linemerge(merged)
    return to_wgs84(merged.simplify(4, preserve_topology=True), crs)


def main():
    _, crs, _, lines_15, lines_30, spaces = build_accessibility()
    features = []
    for index, place in enumerate(spaces.itertuples(), 1):
        geom = place.geometry
        if geom.geom_type not in {"Point", "Polygon", "MultiPolygon"}:
            # OSM may record a park or square as an incomplete outline.
            # Mark it as a point, never falsely fill it as a polygon.
            geom = geom.representative_point()
        geom = geom.simplify(3, preserve_topology=True)
        point = gpd.GeoSeries([geom.representative_point()], crs=crs).to_crs("EPSG:4326").iloc[0]
        name = getattr(place, "name", None)
        if not isinstance(name, str) or not name.strip():
            name = "未命名广场" if place.kind == "square" else "未命名绿地"
        minutes = float(place.walk_min)
        features.append({
            "type": "Feature",
            "id": index,
            "geometry": to_wgs84(geom, crs),
            "properties": {
                "name": name.strip(),
                "kind": place.kind,
                "period": place.period,
                "walk_min": round(minutes, 1) if minutes != float("inf") else None,
                "point_wgs84": [point.x, point.y],
            },
        })

    output = {
        "type": "FeatureCollection",
        "metadata": {
            "title": "成都东站 · 绿地与公共空间可达图",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "OpenStreetMap contributors / OSMnx",
            "coordinate_system": "EPSG:4326 (WGS84)",
            "walk_speed_kmh": round(WALK_SPEED_M_S * 3.6, 1),
            "method": "步行路网最短时间 + 最近可达路口到设施边界的距离；接入路口距边界不超过 200 m。",
            "limits": "未核实实际入口、围墙和开放性；道路上的步行时间为估算值。",
        },
        "station": [LON, LAT],
        "roads": {
            "15": reachable_geometry(lines_15, crs),
            "30": reachable_geometry(lines_30, crs),
        },
        "features": features,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"导出：{OUTPUT}（设施 {len(features)} 处，{OUTPUT.stat().st_size // 1024} KiB）")


if __name__ == "__main__":
    main()

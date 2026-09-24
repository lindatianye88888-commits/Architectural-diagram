"""OSM + 百度地图 + Google Earth 三源核验工作流。

OSM 是可计算的主骨架；百度和 Google Earth 的观察先进入核验清单。
只有 status=verified 且 license_ok=true 的 add_path/block_path 才改变分析图。

运行：
    python osm_three_source_workflow.py run
    python osm_three_source_workflow.py run --refresh
    python osm_three_source_workflow.py self-test
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
from matplotlib import font_manager
from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "data" / "crosscheck_config.json"
EXECUTABLE_ACTIONS = {"add_path", "block_path"}


def configure_plot_fonts() -> None:
    """优先使用仓库其他图纸一致的微软雅黑，避免中文标题缺字。"""
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            font_manager.fontManager.addfont(str(candidate))
            plt.rcParams["font.family"] = font_manager.FontProperties(
                fname=str(candidate)
            ).get_name()
            break
    else:
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans CJK SC", "SimHei"]
    plt.rcParams["axes.unicode_minus"] = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = resolve_path(path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    required = {"project_id", "center", "network_type", "search_radius_m", "paths"}
    missing = sorted(required - config.keys())
    if missing:
        raise ValueError(f"配置缺少字段：{', '.join(missing)}")
    config["_config_path"] = str(config_path)
    return config


def configure_osmnx() -> None:
    ox.settings.timeout = 600
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(ROOT / "cache")


def load_or_fetch_raw_graph(config: dict[str, Any], refresh: bool = False) -> nx.MultiDiGraph:
    """加载固定原始底板；只有首次运行或 --refresh 才访问 OSM。"""
    configure_osmnx()
    raw_path = resolve_path(config["paths"]["raw_graph"])
    if raw_path.exists() and not refresh:
        graph = ox.load_graphml(raw_path)
        graph.graph["raw_graph_origin"] = "saved_snapshot"
        return graph

    center = config["center"]
    graph = ox.graph_from_point(
        (float(center["lat"]), float(center["lon"])),
        dist=float(config["search_radius_m"]),
        network_type=config["network_type"],
    )
    graph.graph["downloaded_at_utc"] = utc_now()
    graph.graph["project_id"] = config["project_id"]
    graph.graph["raw_graph_origin"] = "openstreetmap_download"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(graph, raw_path)

    metadata_path = raw_path.with_suffix(".metadata.json")
    metadata = {
        "project_id": config["project_id"],
        "downloaded_at_utc": graph.graph["downloaded_at_utc"],
        "center_wgs84": [float(center["lon"]), float(center["lat"])],
        "search_radius_m": float(config["search_radius_m"]),
        "network_type": config["network_type"],
        "osmnx_version": ox.__version__,
        "source": "OpenStreetMap contributors",
        "license": "ODbL",
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return graph


def read_observations(path: str | Path) -> list[dict[str, Any]]:
    observation_path = resolve_path(path)
    if not observation_path.exists():
        return []
    payload = json.loads(observation_path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError("核验文件必须是 GeoJSON FeatureCollection。")
    return payload.get("features", [])


def _project_geometry(geometry, target_crs):
    transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    return transform(transformer.transform, geometry)


def _next_override_node_id(graph: nx.MultiDiGraph) -> int:
    numeric = [int(node) for node in graph.nodes if isinstance(node, (int, float))]
    return min(numeric + [0]) - 1


def _override_osmid(observation_id: str, segment_index: int) -> int:
    """生成可被 OSMnx GraphML 重载器接受的稳定负整数。"""
    digest = hashlib.sha1(
        f"{observation_id}:{segment_index}".encode("utf-8")
    ).hexdigest()
    return -int(digest[:12], 16)


def _nearest_node_with_distance(graph: nx.MultiDiGraph, point: Point) -> tuple[Any, float]:
    node = ox.distance.nearest_nodes(graph, X=point.x, Y=point.y)
    node_point = Point(float(graph.nodes[node]["x"]), float(graph.nodes[node]["y"]))
    return node, point.distance(node_point)


def _add_path(
    graph: nx.MultiDiGraph,
    geometry: LineString,
    properties: dict[str, Any],
    snap_tolerance_m: float,
) -> dict[str, Any]:
    if geometry.geom_type != "LineString" or len(geometry.coords) < 2:
        raise ValueError("add_path 必须使用至少含两个坐标的 LineString。")

    coords = list(geometry.coords)
    start_node, start_distance = _nearest_node_with_distance(graph, Point(coords[0]))
    end_node, end_distance = _nearest_node_with_distance(graph, Point(coords[-1]))
    if start_distance > snap_tolerance_m or end_distance > snap_tolerance_m:
        raise ValueError(
            f"新增路径端点离现有路网过远：{start_distance:.1f} m / {end_distance:.1f} m，"
            f"容差为 {snap_tolerance_m:.1f} m。"
        )

    node_ids: list[Any] = [start_node]
    next_node = _next_override_node_id(graph)
    for x, y, *_ in coords[1:-1]:
        graph.add_node(
            next_node,
            x=float(x),
            y=float(y),
            street_count=2,
            source_override=str(properties.get("id", "unnamed")),
        )
        node_ids.append(next_node)
        next_node -= 1
    node_ids.append(end_node)

    actual_coords = [
        (float(graph.nodes[node]["x"]), float(graph.nodes[node]["y"])) for node in node_ids
    ]
    added_length = 0.0
    added_edges = 0
    for index, (u, v) in enumerate(zip(node_ids, node_ids[1:])):
        line = LineString([actual_coords[index], actual_coords[index + 1]])
        if line.length <= 0:
            continue
        attrs = {
            "length": float(line.length),
            "geometry": line,
            "highway": "footway",
            "foot": "yes",
            "oneway": False,
            "osmid": _override_osmid(str(properties.get("id", "unnamed")), index),
            "source_override": str(properties.get("id", "unnamed")),
            "evidence_source": str(properties.get("source", "unknown")),
        }
        graph.add_edge(u, v, **attrs)
        graph.add_edge(v, u, **{**attrs, "geometry": LineString(list(line.coords)[::-1])})
        added_edges += 2
        added_length += line.length
    return {
        "added_directed_edges": added_edges,
        "added_path_length_m": round(added_length, 2),
        "start_snap_m": round(start_distance, 2),
        "end_snap_m": round(end_distance, 2),
    }


def _sample_geometry(geometry, interval_m: float = 20.0) -> list[Point]:
    if geometry.geom_type == "Point":
        return [geometry]
    if geometry.geom_type != "LineString":
        raise ValueError("block_path 只支持 Point 或 LineString。")
    count = max(1, int(math.ceil(geometry.length / interval_m)))
    return [geometry.interpolate(i / count, normalized=True) for i in range(count + 1)]


def _edge_osmid(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value}
    return {str(value)}


def _block_path(
    graph: nx.MultiDiGraph, geometry, snap_tolerance_m: float
) -> dict[str, Any]:
    selected: set[tuple[Any, Any, Any]] = set()
    snap_distances: list[float] = []
    for point in _sample_geometry(geometry):
        edge = ox.distance.nearest_edges(graph, X=point.x, Y=point.y)
        u, v, key = tuple(edge)
        data = graph.get_edge_data(u, v, key) or {}
        edge_line = data.get("geometry") or LineString(
            [
                (graph.nodes[u]["x"], graph.nodes[u]["y"]),
                (graph.nodes[v]["x"], graph.nodes[v]["y"]),
            ]
        )
        distance = point.distance(edge_line)
        if distance <= snap_tolerance_m:
            selected.add((u, v, key))
            snap_distances.append(distance)

    if not selected:
        raise ValueError(
            f"封路几何在 {snap_tolerance_m:.1f} m 容差内没有匹配到路段。"
        )

    to_remove = set(selected)
    for u, v, key in list(selected):
        data = graph.get_edge_data(u, v, key) or {}
        osmids = _edge_osmid(data.get("osmid", ""))
        for candidate_u, candidate_v in ((v, u), (u, v)):
            for candidate_key, candidate_data in (graph.get_edge_data(candidate_u, candidate_v) or {}).items():
                if osmids & _edge_osmid(candidate_data.get("osmid", "")):
                    to_remove.add((candidate_u, candidate_v, candidate_key))

    removed_length = 0.0
    removed = 0
    for u, v, key in to_remove:
        if graph.has_edge(u, v, key):
            removed_length += float(graph[u][v][key].get("length", 0.0))
            graph.remove_edge(u, v, key)
            removed += 1
    return {
        "removed_directed_edges": removed,
        "removed_directed_length_m": round(removed_length, 2),
        "max_snap_m": round(max(snap_distances), 2),
    }


def apply_observations(
    raw_projected: nx.MultiDiGraph,
    observations: list[dict[str, Any]],
    snap_tolerance_m: float,
) -> tuple[nx.MultiDiGraph, list[dict[str, Any]]]:
    graph = copy.deepcopy(raw_projected)
    audit: list[dict[str, Any]] = []
    target_crs = graph.graph["crs"]

    for index, feature in enumerate(observations, 1):
        properties = feature.get("properties") or {}
        observation_id = str(properties.get("id") or f"feature-{index}")
        action = str(properties.get("action", "review"))
        status = str(properties.get("status", "pending"))
        license_ok = properties.get("license_ok") is True
        entry: dict[str, Any] = {
            "id": observation_id,
            "source": properties.get("source", "unknown"),
            "status": status,
            "action": action,
            "license_ok": license_ok,
            "result": "recorded_only",
        }

        if action not in EXECUTABLE_ACTIONS:
            audit.append(entry)
            continue
        if status != "verified":
            entry["result"] = "skipped_not_verified"
            audit.append(entry)
            continue
        if not license_ok:
            entry["result"] = "skipped_license_not_confirmed"
            audit.append(entry)
            continue
        if not feature.get("geometry"):
            entry["result"] = "error"
            entry["error"] = "缺少几何。"
            audit.append(entry)
            continue

        try:
            geometry = _project_geometry(shape(feature["geometry"]), target_crs)
            if action == "add_path":
                details = _add_path(graph, geometry, properties, snap_tolerance_m)
            else:
                details = _block_path(graph, geometry, snap_tolerance_m)
            entry.update(details)
            entry["result"] = "applied"
        except Exception as exc:  # 保留单条失败，其他核验项仍继续处理
            entry["result"] = "error"
            entry["error"] = str(exc)
        audit.append(entry)

    applied = sum(item["result"] == "applied" for item in audit)
    graph.graph["crosscheck_applied"] = applied
    graph.graph["crosscheck_generated_at_utc"] = utc_now()
    return graph, audit


def add_travel_times(graph: nx.MultiDiGraph, speed_kmh: float) -> None:
    speed_m_s = speed_kmh * 1000 / 3600
    for _, _, data in graph.edges(data=True):
        data["length"] = float(data.get("length", 0.0))
        data["travel_time"] = data["length"] / speed_m_s


def accessibility_metrics(
    graph: nx.MultiDiGraph,
    center: dict[str, float],
    speed_kmh: float,
    minutes: list[int],
) -> tuple[dict[str, Any], dict[int, float]]:
    add_travel_times(graph, speed_kmh)
    station = gpd.GeoSeries(
        [Point(float(center["lon"]), float(center["lat"]))], crs="EPSG:4326"
    ).to_crs(graph.graph["crs"]).iloc[0]
    origin = ox.distance.nearest_nodes(graph, X=station.x, Y=station.y)
    cutoff = max(minutes) * 60
    durations = nx.single_source_dijkstra_path_length(
        graph, origin, cutoff=cutoff, weight="travel_time"
    )
    result: dict[str, Any] = {
        "origin_node": str(origin),
        "origin_offset_m": round(
            station.distance(Point(graph.nodes[origin]["x"], graph.nodes[origin]["y"])), 2
        ),
        "graph_nodes": graph.number_of_nodes(),
        "graph_directed_edges": graph.number_of_edges(),
    }
    for value in minutes:
        result[f"reachable_nodes_{value}min"] = sum(
            travel_time <= value * 60 for travel_time in durations.values()
        )
    return result, durations


def _reachable_lines(graph: nx.MultiDiGraph, durations: dict[Any, float], cutoff: float):
    lines = []
    for u, v, data in graph.edges(data=True):
        if min(durations.get(u, math.inf), durations.get(v, math.inf)) > cutoff:
            continue
        lines.append(
            data.get("geometry")
            or LineString(
                [
                    (graph.nodes[u]["x"], graph.nodes[u]["y"]),
                    (graph.nodes[v]["x"], graph.nodes[v]["y"]),
                ]
            )
        )
    return lines


def save_comparison_plot(
    raw_graph: nx.MultiDiGraph,
    verified_graph: nx.MultiDiGraph,
    raw_durations: dict[Any, float],
    verified_durations: dict[Any, float],
    config: dict[str, Any],
) -> Path:
    configure_plot_fonts()
    output = resolve_path(config["paths"]["comparison_png"])
    minutes = max(config.get("analysis_minutes", [15, 30]))
    center = config["center"]
    station = gpd.GeoSeries(
        [Point(center["lon"], center["lat"])], crs="EPSG:4326"
    ).to_crs(raw_graph.graph["crs"]).iloc[0]
    fig, axes = plt.subplots(1, 2, figsize=(14, 7), dpi=160)
    fig.patch.set_facecolor("#fbfaf7")
    for ax, graph, durations, title, color in (
        (axes[0], raw_graph, raw_durations, "原始 OSM", "#58758b"),
        (axes[1], verified_graph, verified_durations, "核验修正后", "#4f8062"),
    ):
        edges = ox.graph_to_gdfs(graph, nodes=False)["geometry"]
        edges.plot(ax=ax, color="#d8d6cf", linewidth=0.35, zorder=1)
        reachable = _reachable_lines(graph, durations, minutes * 60)
        if reachable:
            gpd.GeoSeries(reachable, crs=graph.graph["crs"]).plot(
                ax=ax, color=color, linewidth=0.8, zorder=2
            )
        ax.scatter(station.x, station.y, marker="*", s=90, color="#9a463b", zorder=3)
        span = float(config["search_radius_m"]) * 1.03
        ax.set_xlim(station.x - span, station.x + span)
        ax.set_ylim(station.y - span, station.y + span)
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=14, color="#403d38")
        ax.axis("off")
    fig.suptitle(
        f"{config.get('title', config['project_id'])} · {minutes} 分钟步行路网对比",
        fontsize=18,
        color="#403d38",
    )
    fig.text(
        0.5,
        0.025,
        "核验项只有在 verified 且 license_ok=true 时才进入右图计算",
        ha="center",
        fontsize=9,
        color="#6c6861",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    fig.savefig(output, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return output


def build_verified_graph(
    config_path: str | Path = DEFAULT_CONFIG, refresh: bool = False
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    config = load_config(config_path)
    raw_wgs84 = load_or_fetch_raw_graph(config, refresh=refresh)
    raw_projected = ox.project_graph(raw_wgs84)
    observations = read_observations(config["paths"]["observations"])
    verified, audit_entries = apply_observations(
        raw_projected,
        observations,
        float(config.get("snap_tolerance_m", 60)),
    )
    verified_path = resolve_path(config["paths"]["verified_graph"])
    verified_path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(verified, verified_path)
    summary = {
        "project_id": config["project_id"],
        "generated_at_utc": utc_now(),
        "raw_graph": str(resolve_path(config["paths"]["raw_graph"])),
        "verified_graph": str(verified_path),
        "observation_count": len(observations),
        "applied_count": sum(item["result"] == "applied" for item in audit_entries),
        "observations": audit_entries,
    }
    return verified, summary


def run_workflow(config_path: str | Path = DEFAULT_CONFIG, refresh: bool = False) -> dict[str, Any]:
    config = load_config(config_path)
    raw_wgs84 = load_or_fetch_raw_graph(config, refresh=refresh)
    raw_projected = ox.project_graph(raw_wgs84)
    observations = read_observations(config["paths"]["observations"])
    verified, audit_entries = apply_observations(
        raw_projected,
        observations,
        float(config.get("snap_tolerance_m", 60)),
    )

    minutes = [int(value) for value in config.get("analysis_minutes", [15, 30])]
    speed_kmh = float(config.get("walk_speed_kmh", 4.8))
    raw_metrics, raw_durations = accessibility_metrics(
        raw_projected, config["center"], speed_kmh, minutes
    )
    verified_metrics, verified_durations = accessibility_metrics(
        verified, config["center"], speed_kmh, minutes
    )

    verified_path = resolve_path(config["paths"]["verified_graph"])
    verified_path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(verified, verified_path)
    plot_path = save_comparison_plot(
        raw_projected,
        verified,
        raw_durations,
        verified_durations,
        config,
    )

    summary = {
        "project_id": config["project_id"],
        "generated_at_utc": utc_now(),
        "method": "OSM raw snapshot + licensed verified local overrides",
        "raw_graph": str(resolve_path(config["paths"]["raw_graph"])),
        "verified_graph": str(verified_path),
        "comparison_png": str(plot_path),
        "observation_count": len(observations),
        "applied_count": sum(item["result"] == "applied" for item in audit_entries),
        "raw_metrics": raw_metrics,
        "verified_metrics": verified_metrics,
        "observations": audit_entries,
    }
    audit_path = resolve_path(config["paths"]["audit_json"])
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def run_self_test() -> dict[str, Any]:
    """用离线小路网验证授权门槛、加路和封路逻辑。"""
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:32648"
    graph.add_node(1, x=500000.0, y=3389000.0)
    graph.add_node(2, x=500100.0, y=3389000.0)
    graph.add_node(3, x=500200.0, y=3389000.0)
    for u, v in ((1, 2), (2, 1)):
        line = LineString(
            [(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])]
        )
        graph.add_edge(u, v, osmid=12, length=100.0, geometry=line)

    inverse = Transformer.from_crs("EPSG:32648", "EPSG:4326", always_xy=True)
    p2 = inverse.transform(500100.0, 3389000.0)
    p3 = inverse.transform(500200.0, 3389000.0)
    add_feature = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [p2, p3]},
        "properties": {
            "id": "test-add",
            "source": "field",
            "status": "verified",
            "action": "add_path",
            "license_ok": True,
        },
    }
    guarded_feature = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [p2, p3]},
        "properties": {
            "id": "test-unlicensed",
            "source": "google_earth",
            "status": "verified",
            "action": "add_path",
            "license_ok": False,
        },
    }
    added, audit = apply_observations(graph, [add_feature, guarded_feature], 5.0)
    assert audit[0]["result"] == "applied"
    assert audit[1]["result"] == "skipped_license_not_confirmed"
    assert nx.has_path(added, 1, 3)
    with tempfile.TemporaryDirectory() as directory:
        saved_path = Path(directory) / "verified.graphml"
        ox.save_graphml(added, saved_path)
        reloaded = ox.load_graphml(saved_path)
        assert nx.has_path(reloaded, 1, 3)

    midpoint = inverse.transform(500050.0, 3389000.0)
    block_feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": midpoint},
        "properties": {
            "id": "test-block",
            "source": "field",
            "status": "verified",
            "action": "block_path",
            "license_ok": True,
        },
    }
    blocked, block_audit = apply_observations(graph, [block_feature], 5.0)
    assert block_audit[0]["result"] == "applied"
    assert blocked.number_of_edges() == 0
    return {
        "status": "passed",
        "add_path": audit[0],
        "license_guard": audit[1]["result"],
        "block_path": block_audit[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="运行成都东站三源核验流程")
    run_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    run_parser.add_argument("--refresh", action="store_true", help="重新下载原始 OSM 快照")
    subparsers.add_parser("self-test", help="离线验证修正和授权保护逻辑")
    args = parser.parse_args()

    if args.command == "self-test":
        result = run_self_test()
    else:
        result = run_workflow(args.config, refresh=args.refresh)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

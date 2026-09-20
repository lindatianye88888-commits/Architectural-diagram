"""
OSMnx 真实路网示范（需联网）
抓取峨眉山高铁站周边路网并出图。
dangerouslyDisableSandbox 模式下运行，绕过沙箱出网代理。
"""
import os
import osmnx as ox
import matplotlib.pyplot as plt

# 峨眉山站（高铁）大致坐标
lat, lon = 29.5996, 103.4726
dist = 1500  # 半径(米)

print(f"下载峨眉山站周边 {dist}m 路网……")
G = ox.graph_from_point((lat, lon), dist=dist, network_type="walk")

n_nodes = G.number_of_nodes()
n_edges = G.number_of_edges()
print(f"交叉口: {n_nodes}  路段: {n_edges}")

# 基础形态指标
degrees = [d for _, d in G.degree()]
avg_deg = sum(degrees) / len(degrees)
print(f"平均节点度(交叉口连接数): {avg_deg:.2f}")

fig, ax = plt.subplots(figsize=(10, 10), dpi=200)
fig.patch.set_facecolor("white")
ax.set_facecolor("white")
ox.plot_graph(
    G, ax=ax,
    node_size=0,
    edge_color="#2f3e46",
    edge_linewidth=0.7,
    bgcolor="white",
    show=False, close=False,
)
ax.set_axis_off()
out_png = os.path.join(os.path.dirname(__file__), "emeishan_station_network.png")
plt.savefig(out_png, dpi=200, bbox_inches="tight", facecolor="white")
print(f"已保存: {out_png}")
print("完成。")

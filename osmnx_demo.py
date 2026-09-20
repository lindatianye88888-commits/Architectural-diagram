"""
OSMnx 快速上手示范
适用场景：城市路网 / 步行可达性 / 绿地与水体提取（景观与城市更新分析）

运行：python osmnx_demo.py（首次抓取新区路网需要联网）。

修改 place 即可换城市/片区。默认用峨眉山市做示范（贴合你的峨眉山站前广场项目）。
"""
import os
import osmnx as ox
import matplotlib.pyplot as plt

# 想看哪里就改这里：城市名 / 行政区 / 坐标点都可以
# place = "Chengdu, Sichuan, China"        # 成都全市
place = "Emeishan, Sichuan, China"         # 峨眉山市（示范）
# place = "Wuhou District, Chengdu, China" # 武侯区

# 1) 下载路网（drive=机动车；walk=步行；bike=骑行；all=全部）
print(f"正在下载 {place} 的路网……")
G = ox.graph_from_place(place, network_type="walk")

# 2) 基础指标
stats = ox.graph_to_gdfs(G, nodes=False).describe()
n_nodes = G.number_of_nodes()
n_edges = G.number_of_edges()
print(f"节点数(交叉口): {n_nodes}  边数(路段): {n_edges}")

# 3) 出图：简洁留白风，适合直接放汇报/推文
fig, ax = plt.subplots(figsize=(10, 10), dpi=200)
fig.patch.set_facecolor("white")
ax.set_facecolor("white")
ox.plot_graph(
    G,
    ax=ax,
    node_size=0,          # 不画节点，只留线，更干净
    edge_color="#3a3a3a",  # 深灰路网
    edge_linewidth=0.6,
    bgcolor="white",
    show=False,
    close=False,
)
ax.set_axis_off()
out_png = os.path.join(os.path.dirname(__file__), "osmnx_demo.png")
plt.savefig(out_png, dpi=200, bbox_inches="tight", facecolor="white")
print(f"已保存路网图: {out_png}")

# 4) 顺手提取该区域的绿地与水系（景观项目常用）
try:
    green = ox.features_from_place(place, tags={"leisure": ["park", "garden"]})
    water = ox.features_from_place(place, tags={"natural": ["water", "waterway"]})
    print(f"绿地要素数: {len(green)}  水体要素数: {len(water)}")
except Exception as e:
    print(f"绿地/水体提取跳过: {e}")

print("完成。")

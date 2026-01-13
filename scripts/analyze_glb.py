import trimesh
import os

glb_path = r"d:\work\develop\code\tStudio\docs\robot.glb"

if not os.path.exists(glb_path):
    print(f"Error: File not found at {glb_path}")
else:
    try:
        # 加载 GLB 文件
        scene = trimesh.load(glb_path, force='glb')
        
        print(f"=== GLB Analysis Report for {os.path.basename(glb_path)} ===")
        
        # 1. 检查场景基本信息
        if isinstance(scene, trimesh.Scene):
            print(f"Type: trimesh.Scene")
            print(f"Geometries (Meshes): {len(scene.geometry)}")
            print(f"Nodes in Graph: {len(scene.graph.nodes)}")
            
            # 2. 打印节点层级和名称
            print("\n=== Node Hierarchy & Names ===")
            # 获取所有几何节点的名称
            geometry_nodes = scene.graph.geometry_nodes
            node_names = set()
            
            # 遍历场景图中的节点
            for node in scene.graph.nodes_geometry:
                # trimesh 的 graph 结构中，node 通常是索引或名称
                # 我们尝试获取节点对应的名称属性
                # 注意：trimesh 加载时可能会重命名，我们主要关注是否有预期的 Link 名称
                print(f"- Node: {node}")
                node_names.add(str(node))

            # 3. 检查关键部件是否存在 (基于 TurtleBot3 的常见 Link 名)
            expected_links = ["base_link", "wheel_left_link", "wheel_right_link", "base_scan"]
            print("\n=== Critical Link Check ===")
            for link in expected_links:
                # 模糊匹配，因为可能有前缀或细微差异
                found = any(link in name for name in node_names)
                status = "[OK]" if found else "[MISSING]"
                print(f"{status} {link}")

            # 4. 检查几何体数据量
            print("\n=== Geometry Statistics ===")
            total_vertices = 0
            total_faces = 0
            for name, geom in scene.geometry.items():
                total_vertices += len(geom.vertices)
                total_faces += len(geom.faces)
            print(f"Total Vertices: {total_vertices}")
            print(f"Total Faces: {total_faces}")
            
            if total_vertices > 0:
                print("\n[CONCLUSION] The GLB file contains geometry data and appears to be valid.")
            else:
                print("\n[CONCLUSION] The GLB file is empty (no vertices found).")

        else:
            print(f"Type: {type(scene)} (Expected trimesh.Scene)")
            if hasattr(scene, 'vertices'):
                 print(f"Loaded as single Mesh. Vertices: {len(scene.vertices)}")

    except Exception as e:
        print(f"Error loading GLB: {e}")

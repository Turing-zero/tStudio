from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import trimesh


@dataclass(frozen=True)
class ExtractedRobotAssets:
    """
    表示从机器人资源包中提取的关键资产路径。
    
    Attributes:
        root_dir: 解压后的根目录路径。
        urdf_path: 主 URDF 文件的绝对路径。
        meshes_dir: 存放网格文件 (STL/DAE) 的目录路径，可能为 None。
    """
    root_dir: str
    urdf_path: str
    meshes_dir: str


def _is_within_directory(base_dir: str, target_path: str) -> bool:
    """
    检查目标路径是否位于指定的基准目录内，防止路径遍历攻击。
    
    Args:
        base_dir: 基准目录。
        target_path: 待检查的目标路径。
        
    Returns:
        bool: 如果在目录内返回 True，否则返回 False。
    """
    base_dir_abs = os.path.abspath(base_dir)
    target_abs = os.path.abspath(target_path)
    return os.path.commonpath([base_dir_abs]) == os.path.commonpath([base_dir_abs, target_abs])


def safe_extract_zip(zip_path: str, dest_dir: str) -> None:
    """
    安全地解压 ZIP 文件到指定目录，防止 Zip Slip 漏洞。
    
    Args:
        zip_path: ZIP 文件路径。
        dest_dir: 解压目标目录。
        
    Raises:
        ValueError: 如果 ZIP 包中包含非法的跨目录路径。
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            normalized = member.filename.replace("\\", "/")
            if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
                raise ValueError("invalid zip member path")
            target_path = os.path.join(dest_dir, normalized)
            if not _is_within_directory(dest_dir, target_path):
                raise ValueError("invalid zip member path")
            zf.extract(member, dest_dir)


def find_robot_assets(extracted_root: str) -> ExtractedRobotAssets:
    """
    在解压后的目录中智能查找机器人资产（URDF 和 Meshes）。
    
    会自动评估多个 URDF 文件，选择最可能的主文件（基于文件内容和 Link 定义）。
    
    Args:
        extracted_root: 解压后的根目录。
        
    Returns:
        ExtractedRobotAssets: 包含 URDF 路径和 Mesh 目录的对象。
        
    Raises:
        FileNotFoundError: 如果没有找到任何 URDF 文件。
    """
    urdf_path: Optional[str] = None
    meshes_dir: Optional[str] = None

    # 1. 搜索所有 URDF 文件
    urdf_candidates = []
    for root, dirs, files in os.walk(extracted_root):
        for name in files:
            if name.lower().endswith(".urdf"):
                full_path = os.path.join(root, name)
                urdf_candidates.append(full_path)

    if not urdf_candidates:
        raise FileNotFoundError("urdf not found in zip")

    # 2. 智能选择最佳 URDF
    # 策略：
    # - 排除 common_properties.urdf, materials.urdf 等辅助文件
    # - 优先选择包含 "base_link" 或 "base_footprint" 的文件
    # - 优先选择文件体积较大的 (通常包含更多定义)
    
    best_candidate = None
    best_score = -1

    import xml.etree.ElementTree as ET

    for path in urdf_candidates:
        filename = os.path.basename(path).lower()
        score = 0
        
        # 排除已知辅助文件
        if "common_properties" in filename or "materials" in filename:
            score -= 100
        
        # 基于内容评分
        try:
            tree = ET.parse(path)
            root_node = tree.getroot()
            if root_node.tag == "robot":
                score += 10
            
            # 检查关键 Link
            links = [l.get("name") for l in root_node.findall(".//link")]
            if "base_link" in links or "base_footprint" in links:
                score += 50
            
            # Link 数量越多越可能是主文件
            score += len(links)
            
        except Exception:
            score -= 50
        
        if score > best_score:
            best_score = score
            best_candidate = path
    
    urdf_path = best_candidate
    print(f"[INFO] Selected URDF: {urdf_path} (Score: {best_score})")

    if urdf_path is None:
        # Fallback to first one if all scores are terrible (unlikely)
        urdf_path = urdf_candidates[0]

    candidate_mesh_dirs: List[str] = []
    for root, dirs, files in os.walk(extracted_root):
        for d in dirs:
            if d.lower() == "meshes":
                candidate_mesh_dirs.append(os.path.join(root, d))
    if candidate_mesh_dirs:
        meshes_dir = sorted(candidate_mesh_dirs, key=len)[0]

    # 如果没找到显式的 meshes 目录，但 URDF 存在，可能 mesh 散落在同级或子目录
    # 我们暂且允许 meshes_dir 为 None，后续 resolve_mesh_path 会全盘搜索
    if meshes_dir is None:
        print("[WARN] 'meshes' directory not found, mesh resolution will rely on file search.")
        meshes_dir = extracted_root 

    return ExtractedRobotAssets(root_dir=extracted_root, urdf_path=urdf_path, meshes_dir=meshes_dir)


def _parse_rgba_to_uint8(rgba_str: str) -> List[int]:
    """
    将 URDF 中的 rgba 字符串 (0.0-1.0) 转换为 uint8 数组 (0-255)。
    例如: "1 0 0 1" -> [255, 0, 0, 255]
    支持简单的 Xacro 清理: "${255/255}" -> "1.0"
    """
    # 简单的预处理：去除 Xacro 包装 ${...}
    cleaned_str = rgba_str.replace("${", "").replace("}", "")
    
    parts = cleaned_str.strip().split()
    if len(parts) != 4:
        print(f"[WARN] Invalid rgba format: {rgba_str}, using default white.")
        return [255, 255, 255, 255]
        
    rgba = []
    try:
        for p in parts:
            # 尝试处理简单的数学表达式 (如 255/255)
            if "/" in p:
                num, den = p.split("/")
                v = float(num) / float(den)
            else:
                v = float(p)
            
            v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
            rgba.append(int(round(v * 255.0)))
    except Exception as e:
        print(f"[WARN] Failed to parse rgba '{rgba_str}': {e}. Using default white.")
        return [255, 255, 255, 255]

    return rgba


def extract_mesh_color_map_from_urdf(urdf_path: str) -> Dict[str, List[int]]:
    """
    解析 URDF 文件，提取每个 Mesh 对应的材质颜色。
    
    返回字典: { "wheel.stl": [50, 50, 50, 255], "body.stl": [200, 0, 0, 255] }
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(urdf_path)
    root = tree.getroot()

    # 1. 建立全局材质表: material_name -> rgba
    material_rgba_by_name: Dict[str, List[int]] = {}
    for material in root.findall(".//material"):
        name = material.get("name")
        color_node = material.find("color")
        if not name or color_node is None:
            continue
        rgba_attr = color_node.get("rgba")
        if not rgba_attr:
            continue
        material_rgba_by_name[name] = _parse_rgba_to_uint8(rgba_attr)

    # 2. 遍历所有 Visual 节点，关联 Mesh 文件名与颜色
    mesh_rgba_by_basename: Dict[str, List[int]] = {}
    for visual in root.findall(".//link/visual"):
        geometry_mesh = visual.find("./geometry/mesh")
        if geometry_mesh is None:
            continue
        filename_attr = geometry_mesh.get("filename") or ""
        # 提取文件名 (忽略路径)
        mesh_basename = os.path.basename(filename_attr.replace("\\", "/"))
        if not mesh_basename:
            continue

        rgba: Optional[List[int]] = None
        material = visual.find("./material")
        if material is not None:
            mat_name = material.get("name")
            inline_color = material.find("color")
            
            # 优先使用内联定义的颜色
            if inline_color is not None and inline_color.get("rgba"):
                rgba = _parse_rgba_to_uint8(inline_color.get("rgba"))
            # 其次查找引用的全局材质
            elif mat_name and mat_name in material_rgba_by_name:
                rgba = material_rgba_by_name[mat_name]

        # 默认颜色 (灰色)
        if rgba is None:
            rgba = [200, 200, 200, 255]

        mesh_rgba_by_basename[mesh_basename] = rgba

    return mesh_rgba_by_basename


def iter_stl_files(meshes_dir: str) -> Iterable[str]:
    """
    遍历指定目录及其子目录，生成所有 STL 文件的完整路径。
    
    Args:
        meshes_dir: 要搜索的目录路径。
        
    Yields:
        str: 找到的每一个 STL 文件的绝对路径。
    """
    for root, dirs, files in os.walk(meshes_dir):
        for name in files:
            if name.lower().endswith(".stl"):
                yield os.path.join(root, name)


def bake_zip_to_glb(zip_path: str) -> Tuple[str, str, str]:
    """
    核心流水线：将机器人模型 Zip 包转换为 Web 友好的 GLB 格式。
    基于 URDF 结构解析，支持 STL/DAE，并保留 Link 名称以便 TF 驱动。
    """
    import xml.etree.ElementTree as ET
    
    temp_root = tempfile.mkdtemp(prefix="tstudio_robot_")
    extracted_root = os.path.join(temp_root, "extracted")
    os.makedirs(extracted_root, exist_ok=True)

    # 1. 解压
    safe_extract_zip(zip_path, extracted_root)
    
    # 2. 定位资源
    assets = find_robot_assets(extracted_root)

    # 3. 提取颜色表
    color_map = extract_mesh_color_map_from_urdf(assets.urdf_path)
    
    # 4. 构建 3D 场景 (基于 URDF Link)
    scene = trimesh.Scene()
    
    # 解析 URDF 获取 Link 信息
    tree = ET.parse(assets.urdf_path)
    root = tree.getroot()
    
    # --- Helper Functions ---
    def clean_name(name: str) -> str:
        if not name: return ""
        return name.replace("${namespace}", "").replace("$(arg namespace)", "")

    # 解析 Origin 变换 (xyz rpy) -> Matrix4
    def parse_origin(origin_node) -> np.ndarray:
        mat = np.eye(4)
        if origin_node is None:
            return mat
            
        xyz = origin_node.get("xyz")
        rpy = origin_node.get("rpy")
        
        if xyz:
            tx, ty, tz = map(float, xyz.split())
            mat[:3, 3] = [tx, ty, tz]
            
        if rpy:
            rx, ry, rz = map(float, rpy.split())
            # Euler to Rotation Matrix (XYZ order usually)
            from trimesh.transformations import euler_matrix
            rot_mat = euler_matrix(rx, ry, rz, 'sxyz')
            mat = np.dot(mat, rot_mat)
            
        return mat
    
    # 辅助函数：解析 URDF 路径到本地路径
    def resolve_mesh_path(urdf_mesh_path: str) -> Optional[str]:
        if not urdf_mesh_path: return None
        
        # 1. 规范化路径
        path_to_search = urdf_mesh_path
        if urdf_mesh_path.startswith("package://"):
            parts = urdf_mesh_path.split("/", 3)
            if len(parts) > 3:
                path_to_search = parts[3]
        elif urdf_mesh_path.startswith("file://"):
            path_to_search = urdf_mesh_path.replace("file://", "")
            
        # 2. 尝试直接路径匹配
        possible_paths = [
            os.path.join(extracted_root, path_to_search),
            os.path.join(extracted_root, path_to_search.lstrip("/")),
        ]
        
        if assets.meshes_dir:
             possible_paths.append(os.path.join(assets.meshes_dir, os.path.basename(path_to_search)))

        for p in possible_paths:
            if os.path.exists(p):
                return p

        # 3. 降级：全盘搜索文件名
        basename = os.path.basename(path_to_search)
        for r, _, fs in os.walk(extracted_root):
            if basename in fs:
                return os.path.join(r, basename)
        return None

    # --- Kinematics Tree Building (Fix for Zero Transform Issue) ---
    print(f"[BAKE] Building Kinematics Tree from URDF...")
    parent_map = {} # child_link -> parent_link
    joint_origin_map = {} # child_link -> transform_matrix
    
    for joint in root.findall("joint"):
        parent = joint.find("parent")
        child = joint.find("child")
        if parent is None or child is None:
            continue
            
        parent_link = clean_name(parent.get("link"))
        child_link = clean_name(child.get("link"))
        
        parent_map[child_link] = parent_link
        
        origin = joint.find("origin")
        joint_origin_map[child_link] = parse_origin(origin)

    # Find Root Link
    all_links = set()
    for link in root.findall("link"):
        all_links.add(clean_name(link.get("name")))
        
    root_links = [l for l in all_links if l not in parent_map]
    if not root_links:
        if all_links:
            print("[WARN] No root link found (cycle?), using arbitrary link as root.")
            root_link = list(all_links)[0]
        else:
            print("[ERROR] No links found in URDF!")
            return temp_root, assets.urdf_path, ""
    else:
        root_link = root_links[0]
        
    # Calculate Global Transforms (BFS)
    # T_global_link = T_global_parent * T_joint_origin
    global_transforms = {}
    global_transforms[root_link] = np.eye(4)
    
    queue = [root_link]
    while queue:
        current_link = queue.pop(0)
        current_global = global_transforms[current_link]
        
        # Find children
        children = [child for child, parent in parent_map.items() if parent == current_link]
        
        for child in children:
            t_joint = joint_origin_map.get(child, np.eye(4))
            global_transforms[child] = np.dot(current_global, t_joint)
            queue.append(child)

    print(f"[BAKE] Kinematics Tree Built. Root: {root_link}, Total Links with Transforms: {len(global_transforms)}")

    # --- Process Links and Meshes ---
    print(f"[BAKE] Starting to process URDF Links...")
    processed_count = 0
    
    for link in root.findall(".//link"):
        link_name = clean_name(link.get("name"))
        
        # 一个 Link 可能有多个 Visual 元素
        visuals = link.findall("visual")
        if not visuals:
            continue

        link_meshes = []
        
        for i, visual in enumerate(visuals):
            geometry = visual.find("geometry")
            if geometry is None: continue
            mesh_node = geometry.find("mesh")
            if mesh_node is None: continue
                
            filename = mesh_node.get("filename")
            scale_str = mesh_node.get("scale")
            
            local_path = resolve_mesh_path(filename)
            
            if local_path and os.path.exists(local_path):
                try:
                    # 加载 Mesh
                    mesh = trimesh.load(local_path, force="mesh")
                    
                    if isinstance(mesh, trimesh.Scene):
                        if len(mesh.geometry) == 0: continue
                        mesh = trimesh.util.concatenate(list(mesh.geometry.values()))

                    # 应用 Scale
                    if scale_str:
                        try:
                            parts = scale_str.split()
                            if len(parts) == 3: sx, sy, sz = map(float, parts)
                            elif len(parts) == 1: sx = sy = sz = float(parts[0])
                            else: raise ValueError("Invalid component count")
                            scale_mat = np.eye(4)
                            scale_mat[0,0], scale_mat[1,1], scale_mat[2,2] = sx, sy, sz
                            mesh.apply_transform(scale_mat)
                        except ValueError:
                            print(f"[WARN] Invalid scale format: {scale_str}, skipping scale.")

                    # 应用颜色
                    mesh_basename = os.path.basename(local_path)
                    rgba = color_map.get(mesh_basename, [200, 200, 200, 255])
                    if hasattr(mesh, "visual"):
                        mesh.visual.face_colors = np.array(rgba, dtype=np.uint8)
                    
                    # 应用 Visual Origin (Bake into Mesh Geometry)
                    origin_node = visual.find("origin")
                    transform = parse_origin(origin_node)
                    mesh.apply_transform(transform)
                    
                    link_meshes.append(mesh)
                    
                except Exception as e:
                    print(f"[WARN] Failed to load mesh {filename}: {e}")
                    if filename.lower().endswith('.dae') and "collada" in str(e).lower():
                        print("[HINT] Please install pycollada: pip install pycollada")
                    continue
            else:
                print(f"[WARN] Mesh file not found: {filename}")

        # 合并 Link 下的所有 Mesh
        if link_meshes:
            try:
                if len(link_meshes) == 1:
                    combined_mesh = link_meshes[0]
                else:
                    combined_mesh = trimesh.util.concatenate(link_meshes)
                
                # 应用 Joint Origin via Node Transform
                # 获取该 Link 的全局变换矩阵 (如果找不到，默认为 Identity)
                node_transform = global_transforms.get(link_name, np.eye(4))
                
                # 命名策略：为了保证 TF 驱动，节点名必须包含 Link Name
                scene.add_geometry(combined_mesh, node_name=link_name, geom_name=link_name, transform=node_transform)
                processed_count += 1
            except Exception as e:
                print(f"[ERROR] Failed to merge/add meshes for link {link_name}: {e}")

    print(f"[BAKE] Finished. Processed {processed_count} links (merged). Exporting GLB...")

    # 5. 导出 GLB
    out_glb_path = os.path.join(temp_root, "robot.glb")
    scene.export(out_glb_path)

    return temp_root, assets.urdf_path, out_glb_path


def cleanup_temp_dir(temp_root: str) -> None:
    """清理临时工作目录"""
    if temp_root and os.path.exists(temp_root):
        shutil.rmtree(temp_root, ignore_errors=True)

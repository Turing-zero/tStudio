# 植树机器人全栈数字孪生与可视化技术方案

本文档详细描述了植树机器人项目从建模源头到 Web 端调度的全链路数据流与可视化技术实现方案。本方案旨在解决工程模型（URDF/STL）与 Web 展示模型（GLB）之间的格式鸿沟，构建自动化、轻量化且高保真的数字孪生平台。

## 1. 总体架构设计

### 1.1 架构决策分析 (Architecture Decision Record)

在确定本方案之前，我们深度对比了三种主流的可视化技术路径。基于“植树机器人调度系统”的商业场景与用户画像（操作员而非研发人员），我们做出了以下决策。

| 维度 | 方案一：复刻 RViz (Web版) | 方案二：云渲染 (Pixel Streaming) | 方案三：GLB 烘焙方案 (本方案) |
| --- | --- | --- | --- |
| 技术原理 | 前端解析 URDF + 下载 50+ STL 文件 | 服务器运行 RViz + 推送视频流 | 后端预处理生成 1 个 GLB 文件 |
| 网络开销 | 极高 (Request Storm，50+ HTTP 连接) | 极高 (视频带宽消耗) | 极低 (1 次请求，~5MB 压缩数据) |
| 加载体验 | 零件逐个加载，像“拼图”一样卡顿 | 依赖网速，可能模糊或延迟 | 瞬间完整加载，丝般顺滑 |
| 适用场景 | 研发调试 (需动态修改关节参数) | 高保真仿真/游戏 | 生产调度 / 监控大屏 |
| 决策结论 | ❌ 不推荐 (体验差，难以 CDN 加速) | ❌ 不推荐 (服务器成本过高) | ✅ 强烈推荐 (工业互联网标准做法) |

> **决策核心**：调度系统的核心用户不关心 URDF 结构，只关心“机器人在哪里”。因此，我们拒绝在前端进行繁重的 XML 解析与几何组装，而是将复杂度转移至后端，通过 GLB 交付极致的 Web 体验。

### 1.2 设计目标
*   **单一数据源 (Single Source of Truth)**: 坚持以 SolidWorks 导出的工程文件为源头，避免手动维护多套模型。
*   **端到端自动化**: 实现从“工程师上传”到“Web 端展示”的全自动转换，无需人工干预几何转换或材质修复。
*   **高性能展示**: Web 端加载时间 < 2秒，支持 30fps+ 流畅渲染。
*   **云原生部署**: 适配 K8s/Docker 环境，支持 MinIO 对象存储，符合 12-Factor App 原则。

### 1.2 系统拓扑
```mermaid
graph TD
    subgraph "Engineering (Source)"
        SW[SolidWorks] -->|Export| ZIP[Model ZIP (URDF+STL)]
    end

    subgraph "tStudio Backend (Processing & Serving)"
        API[FastAPI Upload Endpoint]
        Worker[Conversion Pipeline]
        DB[(MySQL Metadata)]
        S3[(MinIO Object Storage)]
    end

    subgraph "Edge / Robot (Runtime)"
        ROS[ROS 2 Humble]
        Nav[Navigation Stack]
    end

    subgraph "tStudio Frontend (Visualization)"
        Web[React / Three.js]
        Loader[GLTFLoader]
    end

    SW --> API
    API --> Worker
    Worker -->|Raw URDF/STL| S3
    Worker -->|Baked GLB| S3
    Worker -->|Metadata| DB
    
    S3 -->|Download URDF| ROS
    S3 -->|Download GLB| Web
    ROS -->|TF/Joint States| Web
```

---

## 2. 数据流与资产管线 (Asset Pipeline)

### 2.1 格式选型标准

| 场景 | 文件格式 | 包含信息 | 优势 | 用途 |
| :--- | :--- | :--- | :--- | :--- |
| **源文件** | **.SLDASM** | 参数化实体 | 工程师编辑 | 设计修改 |
| **物理/仿真** | **.URDF + .STL** | 运动学 + 几何(无色) | ROS 2 原生支持，计算碰撞快 | Gazebo仿真、RViz2调试、碰撞检测 |
| **Web 展示** | **.GLB** | 几何 + **颜色/材质** + 压缩 | 体积极小(STL的1/10)，GPU加载快 | 调度系统监控、数字孪生回放 |

### 2.2 自动化转换流程 (Backend Logic)

当工程师在 tStudio 后台上传 ZIP 包时，后端触发以下处理管线：

1.  **解压与校验**：
    *   解压 ZIP，验证是否包含 `robot.urdf` 及 `/meshes` 目录。
    *   安全检查：防止 Zip Slip 路径遍历攻击。

2.  **URDF 解析与颜色提取**：
    *   解析 URDF XML，提取 `<material>` 标签定义的颜色值。
    *   建立映射表：`{'link_name': {'mesh': 'base.stl', 'color': [255, 100, 0, 255]}}`。

3.  **几何烘焙 (Baking)**：
    *   **核心步骤**：利用 `trimesh` 库加载 STL 网格。
    *   **材质注入**：将 URDF 中定义的颜色“烘焙”到网格顶点或面颜色中（解决 STL 无色问题）。
    *   **压缩导出**：将处理后的网格导出为 `.glb` 格式（二进制压缩，Draco 压缩可选）。

4.  **双路分发存储**：
    *   **路径 A (Raw for ROS)**: 上传原始 URDF/STL 到 MinIO `ros-assets` 桶。
    *   **路径 B (Web for Vis)**: 上传生成的 GLB 到 MinIO `web-assets` 桶。

---

## 3. 存储与数据库设计

### 3.1 存储策略
*   **对象存储 (MinIO)**: 所有模型文件（URDF, STL, GLB）均存储在 MinIO，严禁存储在后端本地文件系统或代码仓库中。
*   **数据库 (MySQL)**: 仅存储元数据（版本号、上传时间、MinIO 访问 URL）。

### 3.2 目录结构规划 (MinIO)

```text
bucket: tree-robot-assets
├── v1.0.0/
│   ├── raw/                <-- 原始文件 (给 ROS 用)
│   │   ├── robot.urdf
│   │   └── meshes/
│   │       ├── base.stl
│   │       └── arm.stl
│   └── web/                <-- 处理后的文件 (给 Web 用)
│       ├── robot.glb       (整机或分体 GLB)
│       └── preview.jpg
└── v1.1.0/
    └── ...
```

### 3.3 数据库表结构 (Schema)

```sql
CREATE TABLE robot_models (
    id INT PRIMARY KEY AUTO_INCREMENT,
    version VARCHAR(50) NOT NULL,          -- 如 "v1.2.0"
    robot_type VARCHAR(50) DEFAULT 'tree_planter',
    
    -- ROS 侧资源路径 (指向 URDF)
    urdf_url VARCHAR(255) NOT NULL,        -- "http://minio.../v1.0.0/raw/robot.urdf"
    
    -- Web 侧资源路径 (指向 GLB)
    display_model_url VARCHAR(255),        -- "http://minio.../v1.0.0/web/robot.glb"
    
    is_active BOOLEAN DEFAULT FALSE,       -- 当前生效版本
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. 关键代码逻辑实现

### 4.1 FastAPI 上传接口 (Python)

```python
from fastapi import UploadFile, BackgroundTasks
import shutil

@app.post("/api/model/upload")
async def upload_robot_model(
    file: UploadFile, 
    version: str, 
    background_tasks: BackgroundTasks
):
    # 1. 临时保存上传的 ZIP
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # 2. 异步触发处理管线（不阻塞 HTTP 响应）
    background_tasks.add_task(process_robot_pipeline, temp_path, version)
    
    return {"status": "processing", "message": "模型正在后台转换中", "version": version}
```

### 4.2 颜色提取与转换脚本 (Core Algorithm)

```python
import trimesh
import xml.etree.ElementTree as ET
import numpy as np
import os

def bake_stl_to_glb(urdf_path, stl_folder, output_folder):
    """
    将无色的 STL 结合 URDF 中的材质信息，转换为带色的 GLB
    """
    # A. 解析 URDF 获取颜色字典
    color_map = {}
    tree = ET.parse(urdf_path)
    # 简化逻辑：假设 visual 节点下包含 geometry(mesh) 和 material(color)
    for visual in tree.findall(".//visual"):
        mesh_node = visual.find(".//geometry/mesh")
        material_node = visual.find(".//material/color")
        
        if mesh_node is not None and material_node is not None:
            filename = os.path.basename(mesh_node.get("filename"))
            rgba_str = material_node.get("rgba").split()
            rgba = [int(float(x) * 255) for x in rgba_str]
            color_map[filename] = rgba

    # B. 转换流程
    for stl_file in os.listdir(stl_folder):
        if not stl_file.endswith('.stl'):
            continue
            
        # 1. 加载几何
        mesh = trimesh.load(f"{stl_folder}/{stl_file}")
        
        # 2. 赋予颜色 (如果 URDF 里没定义，给默认灰色)
        rgba = color_map.get(stl_file, [200, 200, 200, 255])
        if hasattr(mesh, 'visual'):
            mesh.visual.face_colors = np.array(rgba, dtype=np.uint8)
        
        # 3. 导出 GLB
        scene = trimesh.Scene(mesh)
        out_name = stl_file.replace('.stl', '.glb')
        scene.export(f"{output_folder}/{out_name}")
```

---

## 5. 前端 Web 展示方案

### 5.1 渲染技术栈
*   **引擎**: React Three Fiber (Three.js)
*   **加载器**: `useGLTF` (来自 `@react-three/drei`)
*   **状态同步**: 通过 WebSocket 监听 `/tf` 话题，驱动 GLB 模型各部件运动。

### 5.2 加载逻辑
1.  用户打开 tStudio 界面。
2.  前端调用 `/api/model/latest` 获取当前激活模型的 `display_model_url`。
3.  Three.js 直接加载 GLB 文件（利用 CDN/浏览器缓存）。
4.  解析 GLB 场景图，建立 `Link Name -> Object3D` 的索引映射。
5.  在 `useFrame` 循环中，根据 TF 数据更新每个 Object3D 的 `position` 和 `quaternion`。

---

## 6. 部署与运维建议

1.  **MinIO 配置**:
    *   建议配置 Bucket Policy 为 `public` (只读)，以便前端直接通过 URL 访问资源，减轻后端流量压力。
    *   或者使用 Presigned URL 机制进行带签名的安全访问。

2.  **依赖库**:
    *   后端 Docker 镜像需增加 `trimesh`, `numpy`, `scipy`, `networkx` 等几何处理库。

3.  **版本同步机制**:
    *   **运维规范**: 物理机器人更新固件/结构时，必须同步在 tStudio 上传新版模型。
    *   **校验**: 前端可校验 URDF 中的 Joint 名称与 ROS 传来的 TF Frame 是否匹配，不匹配则报警提示“模型版本不一致”。

---

## 7. 方案可行性评估

*   **技术可行性**: `trimesh` 库成熟稳定，STL 转 GLB 方案已在多个开源项目中验证。
*   **性能优势**: GLB 格式相比 STL 无论是网络传输还是 GPU 解析都有数量级的提升。
*   **架构解耦**: 后端作为转换中心，彻底解耦了 ROS 工程端与 Web 展示端，使得两端可以使用各自最优的文件格式。

本方案不仅解决了当前的“显示”问题，更为未来引入数字孪生回放、Web 端仿真调试打下了坚实的数据基础。

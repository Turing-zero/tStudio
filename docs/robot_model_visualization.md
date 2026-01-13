# tStudio RobotModel（URDF）展示方案技术文档

本文档描述在 tStudio 当前已具备 **PointCloud** 与 **TF 坐标系** 展示能力的基础上，引入 **RobotModel（URDF）** 的可行方案与落地步骤。本阶段仅形成技术方案，不涉及代码修改。

## 1. 背景与目标

### 1.1 背景
当前系统可以在 3D 场景中显示：
*   点云（基于可视化插件渲染，支持按 `frame_id` 进行 TF 变换）
*   TF 坐标系树与坐标轴（基于 `TFManager` 管理与渲染）

但尚未支持 RViz 类似的 RobotModel（基于 URDF 的 link/joint 结构及 mesh/primitive 可视化）。

### 1.2 目标
*   在 3D 场景中渲染机器人模型，并随 TF 实时更新各 link 位姿
*   支持至少一种“可用、稳定、易部署”的模型来源方式（优先保证落地）
*   提供可配置能力（启用/禁用、frame 前缀/映射、透明度/颜色等）

### 1.3 非目标（本阶段不做）
*   不修改现有业务代码与功能逻辑
*   不承诺一次性实现完整的 `package://` 资源解析与所有 mesh 格式支持
*   不实现复杂交互（选中 link 联动参数面板等），仅给出后续扩展点

## 2. 现有能力与约束

### 2.1 TF 数据链路已具备
*   前端收到 `/tf`、`/tf_static` 后会调用 `tfManager.updateTF()` 更新帧树与缓存
*   可视化对象可以通过 `tfManager.getTransform(frameId, rootFrame)` 获取世界位姿

### 2.2 3D 场景支持长期挂载对象
*   3D 场景组件支持渲染任意 React Three Fiber 的 `<group>/<mesh>` 结构
*   已存在加载 glb 模型并按姿态驱动的实现先例（IMU 模型）

### 2.3 当前缺口
*   没有 RobotModel 的“模型源”（URDF/mesh 的获取与加载）
*   没有 RobotModel 的“场景挂载与更新机制”（将 URDF link 对象挂载到 Scene3D 并按 TF 更新）

## 3. 总体架构方案（推荐）

RobotModel 更接近“场景级对象”，其更新驱动来自 TF（全局），不必强绑定某个 topic 的消息渲染。因此建议引入“场景级 RobotModel 组件”，与现有 topic 可视化并行。

### 3.1 组件划分
*   **RobotModelManager（前端）**
    *   负责：加载/解析 URDF、构建 `THREE.Group`（每个 link 一个子节点）、维护 `linkName -> Object3D` 索引
*   **RobotModelView（前端 React 组件）**
    *   负责：将 RobotModelManager 的根 `Group` 挂载到 Scene3D
    *   负责：每帧（`useFrame`）根据 `tfManager` 更新各 link 的 position/quaternion

### 3.2 更新逻辑（核心）
*   从 URDF 中得到 `link_name` 列表
*   对每个 link：按规则得到其 TF frame 名称（默认等同于 `link_name`，可配置 prefix/remap）
*   每帧调用 `tfManager.getTransform(linkFrame, tfManager.getRootFrame())`，更新对应 Object3D

## 4. 模型来源方案对比

| 方案 | 输入 | 显示内容 | 优点 | 主要风险/代价 | 推荐度 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A：URDF + primitive（先落地）** | URDF XML | `box/cylinder/sphere` 或降级几何 | 不依赖 `package://`；浏览器端稳定；最快验证 TF 正确性 | 外观不真实；对复杂机器人表达有限 | ⭐⭐⭐⭐⭐ |
| **B：URDF + mesh（生产级）** | URDF XML + mesh（stl/dae/obj） | 真实外观 | 接近 RViz；可展示完整模型 | 需解决 `package://` 到 URL 映射；资源托管、安全与缓存复杂 | ⭐⭐⭐ |
| **C：离线导出 glb（工程折中）** | 单个 `robot.glb`（离线转换） | 真实外观（整机或分件） | 前端最简单；加载/性能好；部署稳定 | 更新模型需重新导出；关节/层级语义弱化 | ⭐⭐⭐⭐ |

结论：按“先可用再完整”的节奏，优先实现 **方案 A**，后续按需求演进到 **B** 或 **C**。

## 5. 推荐落地路径（阶段化计划）

### 5.1 第一阶段：方案 A（URDF primitive）
目标：在不依赖 mesh 的前提下，让 RobotModel 在 3D 场景中正确跟随 TF。
*   解析 URDF：获取 link 列表与 `<visual>` 的几何描述
*   为每个 link 创建基础几何体（box/cylinder/sphere；缺失则用占位几何）
*   按 TF 更新 link 位姿（验证与点云/TF 坐标一致）

### 5.2 第二阶段：方案 B（URDF + mesh）
目标：支持常见 mesh 资源加载，并能在浏览器端渲染。
*   定义资源映射策略（`package://`/相对路径 -> http(s) URL）
*   引入受控资源下载/静态托管（后端实现路由与白名单策略）
*   增加缓存与错误降级（加载失败 fallback 到 primitive）

### 5.3 第三阶段：体验与工具化
目标：增强可用性、可观测性与运维体验。
*   增加显示控制：按 link 分组开关、透明度、颜色、线框模式
*   增加调试能力：与 TF Tree 联动高亮/定位、显示缺失 TF 的 link 列表
*   性能优化：对象池复用、按需更新、降低每帧遍历成本（在 TF 更新频率高时尤其重要）

## 6. 配置设计（建议）

RobotModel 作为场景级对象，建议以“场景插件配置”或“全局可视化配置”承载，最低需要以下参数：

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `enabled` | boolean | `false` | 是否启用 RobotModel 渲染 |
| `source` | enum | `urdf_param` | `urdf_param`/`urdf_text`/`glb_url` |
| `rootFrame` | string | `tfManager.getRootFrame()` | 参考系，决定模型在世界中的最终位姿基准 |
| `framePrefix` | string | `""` | 将 link 名映射为 `prefix + link`（解决 namespace） |
| `frameRemap` | map | `{}` | 精确映射：`{ "base_link": "robot1/base_link" }` |
| `alpha` | number | `1.0` | 透明度（0~1） |
| `defaultColor` | string | `#cccccc` | 默认材质颜色 |
| `missingTfPolicy` | enum | `hide` | `hide`/`freeze`/`showOrigin` |

## 7. URDF 获取与资源解析（建议接口，不在本阶段实现）

### 7.1 获取 URDF（推荐优先顺序）
1.  **从 ROS 参数 `/robot_description` 获取**（最接近 RViz 的使用习惯）
2.  **前端直接粘贴/上传 URDF 文本**（适用于 rosapi 不可用或权限受限场景）
3.  **直接指定 glb URL**（走方案 C）

### 7.2 `package://` 资源映射（方案 B 的关键）
URDF 中常见：`package://my_robot_description/meshes/link.stl`。浏览器无法直接解析该 URI，需要映射为 HTTP 可访问地址。

建议策略：
*   后端提供“受控资源网关”接口，将 `package://` 解析为服务器本地路径并以二进制流返回
*   仅允许访问白名单目录（例如：ROS workspace 的 `install/share`、`src` 中的 description 包）
*   做路径规范化与禁止 `..` 穿越，防止任意文件读取

示例接口（建议）：
*   `GET /api/robot_model/urdf?source=robot_description`
*   `GET /api/robot_model/resource?uri=package://...`

## 8. 风险与对策

| 风险 | 现象 | 对策 |
| :--- | :--- | :--- |
| TF frame 命名不一致 | URDF link 叫 `base_link`，TF 实际是 `robot/base_link` | 提供 `framePrefix` 与 `frameRemap` |
| TF 不完整或延迟 | 部分 link 不显示/抖动 | `missingTfPolicy` + 缺失列表提示；优先消费 `/tf_static` |
| 坐标基变换不一致 | 模型朝向与点云/TF 轴不一致 | RobotModel 严格复用 `tfManager.getTransform()` 输出，不单独做轴变换 |
| Mesh 资源不可达 | `package://` 无法加载 | 先做方案 A；方案 B 必须先落地资源网关与白名单 |
| 性能瓶颈 | link 多、TF 高频导致掉帧 | 仅在 TF 更新时刷新缓存；减少每帧遍历；合并材质与几何体 |

## 9. 验收标准（建议）

### 9.1 第一阶段（方案 A）
*   机器人模型在 3D Scene 中可显示（primitive/占位即可）
*   TF 更新时模型随之运动，且与点云/TF 轴对齐一致
*   支持至少一种 frame 映射配置（`framePrefix` 或 `frameRemap`）

### 9.2 第二阶段（方案 B 或 C）
*   至少一种 mesh 来源可正常加载（受控 URL 或 glb）
*   资源不可达时有明确降级与告警策略（不导致场景崩溃）

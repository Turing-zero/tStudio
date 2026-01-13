# tStudio 开发与生产环境日志及启动方案文档

本文档总结了 tStudio 从本地开发模式到云原生生产环境的全生命周期管理方案，重点包含**双模日志架构**与**环境差异化启动流程**。

## 1. 架构级日志方案

我们将日志系统升级为符合 **12-Factor App** 标准的企业级架构，支持开发与生产环境的自动适配。

### 1.1 核心设计理念
*   **双模日志格式**：
    *   **开发模式 (DEV)**：保持人类可读的 `text` 格式（时间-级别-消息）。
    *   **生产模式 (PROD)**：自动切换为 `JSON` 结构化格式，对接 ELK/Filebeat，无需 Grok 解析。
*   **零文件依赖**：
    *   所有日志统一输出到 **Stdout (标准输出)**。
    *   **禁止**应用自身写本地日志文件，避免容器存储问题。
*   **动态配置**：
    *   使用 Python `dictConfig` 替代静态 YAML，支持 `ENV` 环境变量动态注入。

### 1.2 代码变更清单

| 变更模块 | 涉及文件 | 变更说明 |
| :--- | :--- | :--- |
| 配置中心 | `backend/log_config.py` | 新增模块。实现 `json/text` 格式自适应切换，预留 `TraceIdFilter`。 |
| 入口注入 | `backend/main.py` | 在 `app` 启动前优先加载日志配置，接管 Uvicorn 系统日志。 |
| 依赖管理 | `backend/requirements.txt` | 新增 `python-json-logger`。 |

---

## 2. 环境启动方案对比

针对不同环境的性能与调试需求，我们设计了差异化的启动流程。

### 2.1 差异对比矩阵

| 特性 | 开发环境 (Development) | 生产环境 (Production) |
| :--- | :--- | :--- |
| 启动命令 | `make dev` | `make prod` |
| 前端模式 | `npm start` (热重载服务器) | `npm run build` (编译为静态资源) |
| 后端模式 | `python main.py` (单进程, Reload=True) | `uvicorn` (多进程 Workers, Reload=False) |
| 日志格式 | Text (彩色文本) | JSON (结构化) |
| 并发模型 | 单进程调试 | 多进程高并发 (`--workers 4`) |

### 2.2 Makefile 使用指南

我们通过 `Makefile` 封装了所有操作，确保操作一致性。

#### 开发环境 (Development)
```bash
make dev
```
*   **行为**：
    1.  并行启动前端开发服务器（`localhost:3000`）和后端 API 服务（`localhost:3500`）。
    2.  后端代码修改后自动重启（Hot Reload）。
    3.  日志以彩色文本输出到终端。

#### 生产环境 (Production)
```bash
make prod
```
*   **行为**：
    1.  **构建前端**：执行 `npm run build` 生成静态文件（位于 `frontend/build`）。
    2.  **启动后端**：
        *   命令：`uvicorn main:app --host 0.0.0.0 --port 3500 --workers 4`
        *   环境变量：自动注入 `ENV=PROD`。
    3.  **日志**：强制转变为 JSON 格式。
*   **注意**：在真实的 Docker/K8s 部署中，通常只使用 `make build-frontend` 和 `make prod-backend` 分步构建镜像。

### 2.3 验证方法
*   **开发验证**：运行 `make dev`，检查控制台是否为彩色文本日志。
*   **生产模拟**：运行 `make prod`，检查：
    1.  前端是否完成 Build 流程。
    2.  后端日志是否转变为 `{"asctime": "...", ...}` 的 JSON 格式。

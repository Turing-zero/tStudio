# tStudio 技术架构与设计文档

## 1. 架构概览 (Architecture Overview)

tStudio 采用混合微服务架构，前端基于 React，后端基于 Python FastAPI，并设计为可集成到更大的 Java Spring Cloud 微服务体系中。

### 1.1 系统拓扑
```mermaid
graph TD
    User[用户浏览器] --> |HTTP/WebSocket| Frontend[tStudio Frontend (React)]
    Frontend --> |REST API| Backend[tStudio Backend (FastAPI)]
    Frontend --> |WebSocket| Backend
    Backend --> |roslibpy| ROS[ROS Bridge / Robot]
    
    subgraph "Microservices Context"
        JavaGateway[Java API Gateway] --> |HTTP| Backend
        Backend -.-> |Logs| ELK[ELK Stack]
        Backend -.-> |Register| Nacos_K8s[Nacos / K8s Service]
    end
```

## 2. 微服务集成策略 (Microservices Integration)

由于 tStudio (Python) 需要与企业级 Java Spring Cloud 体系共存，我们制定了以下集成策略。

### 2.1 服务发现与注册
我们对比了两种主流方案，架构设计兼容两者，目前推荐 **方案二**（云原生方向）。

| 特性 | 方案一：Nacos 注册 (应用层融合) | 方案二：K8s Service (基础设施融合) |
| :--- | :--- | :--- |
| **原理** | Python 使用 `nacos-sdk-python` 主动注册到 Nacos | K8s Service 自动暴露 Python Pod，Java 通过 DNS 调用 |
| **侵入性** | 高 (代码需依赖 Nacos SDK) | 低 (完全解耦，由运维配置) |
| **维护成本** | 高 (需维护 SDK 版本、心跳保活) | 低 (K8s 原生能力) |
| **适用场景** | 传统虚拟机部署，强依赖 Spring Cloud 治理 | 容器化/K8s 部署，追求多语言无关性 |

**结论**：优先支持 K8s Service 模式。Python 服务专注于提供 REST 接口，不引入复杂的注册中心客户端逻辑。

### 2.2 服务间通信
*   **协议**：HTTP RESTful API。
*   **调用方向**：Java 服务 -> Python 服务 (tStudio)。
*   **负载均衡**：
    *   **Nacos 模式**：Java 端的 Ribbon/LoadBalancer 负责。
    *   **K8s 模式**：K8s Service (ClusterIP) 负责。

## 3. 可观测性与日志策略 (Observability & Logging)

为了适应云原生环境及 ELK (Elasticsearch, Logstash, Kibana) 采集需求，我们实施了严格的日志规范。

### 3.1 日志架构决策
*   **核心原则**：日志不落盘，全部输出到 **标准输出 (Stdout/Stderr)**。
*   **采集方式**：由 K8s DaemonSet (如 Filebeat/Fluentd) 采集容器标准输出。
*   **格式规范**：
    *   **生产环境 (PROD)**：**JSON 格式** (包含 `trace_id`, `timestamp`, `level`, `filename`, `lineno`)。
    *   **开发环境 (DEV)**：**文本彩色格式** (人类可读)。

### 3.2 实现细节 (`backend/log_config.py`)
我们使用 Python 标准库 `logging.config.dictConfig` 进行配置，而非静态 YAML 文件，以实现动态环境变量注入。

*   **依赖库**：`python-json-logger`。
*   **环境变量控制**：
    *   `ENV`: `PROD` 开启 JSON，其他开启 Text。
    *   `LOG_LEVEL`: 控制日志级别 (DEBUG/INFO/WARN/ERROR)。
*   **链路追踪 (Future Work)**：
    *   预留了 `TraceIdFilter`。
    *   未来将通过 Middleware 解析 HTTP Header (`X-B3-TraceId` 或 `traceparent`)，注入 `contextvars`，实现跨语言的全链路追踪。

## 4. 后端核心设计 (Backend Core Design)

### 4.1 异步与并发模型
*   **Web 框架**：FastAPI (基于 Starlette/Uvicorn)，原生支持 `async/await`。
*   **ROS 连接**：由于 `roslibpy` 的 `run()` 方法是阻塞的且与 `asyncio` 事件循环冲突，我们采用了 **独立守护线程 (Daemon Thread)** 模式。
    *   **代码位置**：`backend/adapters/ros_adapter.py`
    *   **机制**：`threading.Thread(target=run_ros, daemon=True)` 负责维护 ROS 连接，主线程通过非阻塞方式检查连接状态。

### 4.2 配置管理
*   **策略**：**代码字典配置 (dictConfig)** 优于 `logging.yaml`。
*   **理由**：
    1.  天然支持读取 `os.getenv`，适应 K8s ConfigMap 注入。
    2.  避免引入 `PyYAML` 依赖。
    3.  符合 12-Factor App 的 "Store config in the environment" 原则。

### 4.3 模块化适配器
*   **设计**：`DataSourceManager` 管理多种适配器 (ROS, Mock, File)。
*   **扩展性**：通过继承 `BaseAdapter` 可轻松扩展新的数据源（如 MQTT, HTTP Polling）。

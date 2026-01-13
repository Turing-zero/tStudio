# 植树机器人调度系统 MinIO 对象存储技术方案 (V1.0.0)

本文档基于项目当前的 FastAPI + React 架构，结合植树机器人“数字孪生”与“远程运维”的实际需求，制定 MinIO 对象存储的技术选型、部署及后端集成方案。

## 目录
- [1. 技术选型理由](#1-技术选型理由)
- [2. MinIO 容器化部署方案](#2-minio-容器化部署方案)
- [3. FastAPI 后端集成方案 (Python)](#3-fastapi-后端集成方案-python)
- [4. 植树调度系统具体应用场景](#4-植树调度系统具体应用场景)

---

## 1. 技术选型理由

在植树机器人调度系统中，MinIO 将承载核心的 **非结构化数据** 存储中心角色，主要存储对象包括：

1.  **3D 数字孪生资产**：`.glb` (Web 展示模型)、`.stl` (物理仿真模型)、`.urdf` (机器人描述文件)。
2.  **视觉监控数据**：机器人回传的实时作业照片、延时摄影视频（用于生长监控）。
3.  **运维数据**：机器人系统日志 (`.log.gz`)、OTA 升级固件包。

**选择 MinIO 的核心优势**：

*   **私有化与边缘部署**：植树作业区往往网络受限或处于内网环境。MinIO 是单二进制文件，极度轻量，可直接部署在园区本地服务器甚至工控机上，无需依赖公有云。
*   **S3 协议原生兼容**：MinIO 是事实上的 S3 标准开源实现。使用标准的 AWS SDK 开发，未来若业务上云（迁移至阿里云 OSS、AWS S3），仅需修改配置文件，**零代码修改**。
*   **高性能吞吐**：在标准硬件下读写速率可达 55GB/s+，能够轻松应对数百台机器人并发上传高清监控图片和日志的需求。
*   **数据可靠性**：内置 **纠删码 (Erasure Code)** 技术，即使损坏 N/2 块硬盘，数据依然可恢复，保障核心资产（如历史生长记录）不丢失。
*   **事件驱动能力**：支持 Webhook 通知。例如：当机器人上传一张新照片，MinIO 可自动触发后端 AI 服务进行“树苗存活率分析”。

## 2. MinIO 容器化部署方案

采用 Docker 部署，确保环境隔离与快速迁移。

### 2.1 环境要求
*   **OS**: Ubuntu 22.04 LTS / CentOS 7+ / Windows (WSL2)
*   **Runtime**: Docker Engine 20.10+
*   **版本确认**:
    ```bash
    docker --version
    # 输出示例: Docker version 24.0.5, build ced0996
    ```

### 2.2 MinIO 容器化部署方案 (基础单机版)

采用 Docker 部署，确保环境隔离与快速迁移。此方案适合**开发环境**或**非核心业务**的生产环境。

#### 2.2.1 生产级启动脚本 (已修正)
> **注意**：已替换旧版 `MINIO_ACCESS_KEY` 为新版 `MINIO_ROOT_USER`，并增加 Console 端口映射。

```bash
docker run -p 9000:9000 -p 9001:9001 \
  --name minio \
  -d --restart=always \
  -e "MINIO_ROOT_USER=admin" \
  -e 'MINIO_ROOT_PASSWORD=TreeRobot_2026_Secure!' \
  -v /mnt/data/minio_data:/data \
  -v /mnt/config/minio_config:/root/.minio \
  minio/minio server /data --console-address ":9001"
```

#### 2.2.2 参数详解
*   **端口映射**：
    *   `9000`: **API 数据端口** （FastAPI 后端、ROS 机器人连接使用）。
    *   `9001`: **Web 控制台端口** （运维人员通过浏览器管理 Bucket 使用）。
*   **环境变量**：
    *   `MINIO_ROOT_USER`: `admin` (超级管理员账号)
    *   `MINIO_ROOT_PASSWORD`: `TreeRobot_2026_Secure!` (超级管理员密码)
*   **挂载卷**：
    *   `/mnt/data/minio_data`: 映射宿主机大容量磁盘，数据持久化存储。

**最佳实践**：虽然 Docker 会自动创建不存在的目录，但建议在启动前手动创建并确认挂载点，以避免权限问题或误用系统盘。

```bash
sudo mkdir -p /mnt/data/minio_data /mnt/config/minio_config
# 检查 /mnt/data 是否挂载了独立磁盘
df -h /mnt/data
```

#### 2.2.3 验证
访问 `http://<服务器IP>:9001`，使用上述账号密码登录。如果能看到 Dashboard，即部署成功。

**预期日志输出**：
首次启动时看到以下日志是**正常**的：
*   `Formatting 1st pool`: 表示新数据盘初始化成功。
*   `WARNING: Host local has more than 0 drives...`: 提示单点部署无数据冗余（生产环境单机部署时的正常提示，无需处理）。

---

### 2.3 MinIO 集群部署方案 (进阶高可用版)

部署 MinIO 集群（Distributed MinIO）的核心在于利用 **纠删码（Erasure Coding）** 技术。为了提供最高的数据安全性和可用性，官方推荐至少需要 **4 个驱动器（Drives）**。

#### 方案 A：使用 Docker Compose 部署单机伪集群 (推荐用于开发)

这种方式会在单台机器上启动 4 个 MinIO 容器，组成一个模拟集群。

**1. 创建目录和文件**

```bash
mkdir -p ~/minio-cluster
cd ~/minio-cluster
touch docker-compose.yml nginx.conf
```

**2. 编写 `docker-compose.yml`**

```yaml
version: '3.8'

services:
  # 定义 4 个 MinIO 节点
  minio1:
    image: minio/minio
    hostname: minio1
    volumes:
      - ./data1:/data
    command: server http://minio{1...4}/data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=TreeRobot_2026_Secure!
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  minio2:
    image: minio/minio
    hostname: minio2
    volumes:
      - ./data2:/data
    command: server http://minio{1...4}/data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=TreeRobot_2026_Secure!

  minio3:
    image: minio/minio
    hostname: minio3
    volumes:
      - ./data3:/data
    command: server http://minio{1...4}/data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=TreeRobot_2026_Secure!

  minio4:
    image: minio/minio
    hostname: minio4
    volumes:
      - ./data4:/data
    command: server http://minio{1...4}/data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=TreeRobot_2026_Secure!

  # 使用 Nginx 作为统一入口 (负载均衡)
  nginx:
    image: nginx:latest
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    ports:
      - "9000:9000" # API 端口
      - "9001:9001" # 控制台端口
    depends_on:
      - minio1
      - minio2
      - minio3
      - minio4
```

**3. 编写 `nginx.conf` (负载均衡配置)**

```nginx
user  nginx;
worker_processes  auto;

events {
    worker_connections  1024;
}

http {
    upstream minio_api {
        server minio1:9000;
        server minio2:9000;
        server minio3:9000;
        server minio4:9000;
    }

    upstream minio_console {
        server minio1:9001;
        server minio2:9001;
        server minio3:9001;
        server minio4:9001;
    }

    server {
        listen 9000;
        location / {
            proxy_pass http://minio_api;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # 支持 WebSocket (Console 需要)
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }

    server {
        listen 9001;
        location / {
            proxy_pass http://minio_console;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

**4. 启动集群**

```bash
docker-compose up -d
```

#### 方案 B：多台物理机/虚拟机部署 (生产环境标准)

假设您有 4 台服务器，IP 分别为 `192.168.1.101` 到 `192.168.1.104`。**每台机器**上都需要执行以下步骤：

**1. 准备工作**

* **磁盘格式化**：MinIO 强烈推荐使用 **XFS** 文件系统格式化数据盘。
```bash
mkfs.xfs /dev/sdb
mkdir -p /mnt/data
mount /dev/sdb /mnt/data
```

* **时间同步**：确保所有机器安装了 `chrony` 或 `ntp`，时间误差不能超过 3 秒。
* **Hosts 解析**：在每台机器的 `/etc/hosts` 添加：
```text
192.168.1.101 minio1
192.168.1.102 minio2
192.168.1.103 minio3
192.168.1.104 minio4
```

**2. 下载 MinIO 二进制文件**

```bash
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio
sudo mv minio /usr/local/bin/
```

**3. 创建 systemd 服务文件**

创建用户并设置权限：
```bash
groupadd -r minio-user
useradd -m -r -g minio-user minio-user
chown minio-user:minio-user /mnt/data
```

创建配置文件 `/etc/default/minio` (**这是集群配置的核心**):
```bash
# 这一行定义了集群拓扑。{1...4} 会自动展开。
# 意思是：本集群由 minio1 到 minio4 这4台机器组成，数据都在 /mnt/data 目录下
MINIO_VOLUMES="http://minio{1...4}:9000/mnt/data"

# 管理后台端口
MINIO_OPTS="--console-address :9001"

# 账号密码（所有节点必须完全一致！）
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=TreeRobot_2026_Secure!
```

创建服务文件 `/etc/systemd/system/minio.service`:
```ini
[Unit]
Description=MinIO
Documentation=https://docs.min.io
Wants=network-online.target
After=network-online.target

[Service]
User=minio-user
Group=minio-user
EnvironmentFile=/etc/default/minio
ExecStart=/usr/local/bin/minio server $MINIO_OPTS $MINIO_VOLUMES
Restart=always
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

**4. 启动集群**

在 **所有 4 台机器** 上执行：
```bash
sudo systemctl enable minio
sudo systemctl start minio
```

---

### 2.4 常见问题排查 (Troubleshooting)

**Q: 登录提示 `{"message":"invalid login"}` 或密码错误？**

这通常是因为**数据目录中残留了旧的配置数据**。MinIO 启动时如果检测到配置目录非空，会优先使用已有的账号密码，**忽略**环境变量中新设置的 `MINIO_ROOT_PASSWORD`。

> **典型现象**：日志中出现 `Formatting 1st pool` (表示数据盘是新的)，但登录依然失败。这说明**配置盘 (`/mnt/config`) 未被清理**，MinIO 使用了旧密码。

*   **尝试 1**：使用默认账号密码 `minioadmin` / `minioadmin` 登录。
*   **尝试 2**：查看容器启动日志，确认当前生效的密码：
    ```bash
    docker logs minio
    ```
*   **尝试 3 (仅限新环境)**：如果确认数据可删除，请彻底清理挂载目录后重试：
    ```bash
    # 1. 停止并删除容器
    docker rm -f minio
    # 2. 清理挂载数据 (⚠️注意：这将删除所有已上传文件和配置!)
    # 务必删除整个目录再重建，以确保清除 .minio.sys 等隐藏文件
    sudo rm -rf /mnt/data/minio_data /mnt/config/minio_config
    sudo mkdir -p /mnt/data/minio_data /mnt/config/minio_config
    # 3. 重新运行启动命令
    ```

## 3. FastAPI 后端集成方案 (Python)

后端采用 Python (FastAPI) 与 MinIO 交互，处理模型转换后的上传及前端的下载请求。

### 3.1 依赖安装
在 `backend/requirements.txt` 中添加：
```text
minio
pydantic
python-multipart
```

### 3.2 配置管理 (`backend/core/env_config.py`)
使用 Pydantic 管理配置，支持从环境变量覆盖，符合 12-Factor 原则。

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # MinIO 配置
    MINIO_ENDPOINT: str = "127.0.0.1:9000"      # 注意：不要带 http://
    MINIO_ACCESS_KEY: str = "admin"             # 对应 MINIO_ROOT_USER
    MINIO_SECRET_KEY: str = "TreeRobot_2026_Secure!" # 对应 MINIO_ROOT_PASSWORD
    MINIO_BUCKET_NAME: str = "tree-robot-assets"
    MINIO_SECURE: bool = False                  # 内网部署通常为 False (HTTP)

    class Config:
        env_file = ".env"

settings = Settings()
```

### 3.3 工具类封装
为支持未来扩展（如切换至 OSS/S3），采用适配器模式设计。

#### 3.3.1 抽象基类 (`backend/services/storage/adapter.py`)
定义标准接口规范，所有云存储实现必须遵循此契约。

```python
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Union, BinaryIO

class StorageAdapter(ABC):
    @abstractmethod
    def upload_file(self, file_data: Union[bytes, BinaryIO], filename: str, content_type: str, folder: str) -> str:
        """上传文件并返回访问 URL"""
        pass
    
    # ... 其他标准接口 (exists, list, presign_url)
```

#### 3.3.2 MinIO 实现 (`backend/services/storage/minio_impl.py`)
实现 `StorageAdapter` 接口，封装 MinIO 官方 SDK。

```python
from minio import Minio
from core.env_config import settings
from .adapter import StorageAdapter

class MinioAdapter(StorageAdapter):
    # ... 具体实现代码 ...

# 单例导出
minio_handler = MinioAdapter()
```

#### 3.3.3 模块导出 (`backend/services/storage/__init__.py`)
通过 `__init__.py` 暴露统一接口，方便外部调用。

```python
from .adapter import StorageAdapter
from .minio_impl import MinioAdapter, minio_handler

__all__ = ["StorageAdapter", "MinioAdapter", "minio_handler"]
```

### 3.4 接口实现 (`backend/api/api_storage.py`)

```python
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from services.storage import minio_handler  # 引用模块化后的 handler

router = APIRouter()
# ... 路由实现代码 ...
```

### 3.4 接口实现 (`backend/api/api_storage.py`)

提供两种上传模式：
1.  **代理上传 (Proxy Upload)**: 适合小文件 (如 < 5MB)，后端可完全控制文件处理逻辑。
2.  **预签名上传 (Presigned URL)**: 适合大文件 (如 3D 模型)，前端直接上传到 MinIO，减轻后端带宽压力。

```python
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from services.minio import minio_handler

router = APIRouter()

@router.post("/model/upload", tags=["MinIO Storage"])
async def upload_robot_model(file: UploadFile = File(...)):
    """
    [代理上传] 处理 GLB 模型上传 (通常由转换管线调用)
    注意：MinIO SDK 是同步的，必须使用 run_in_threadpool 避免阻塞 Event Loop
    """
    try:
        content = await file.read()
        
        # 在线程池中执行同步上传操作
        url = await run_in_threadpool(
            minio_handler.upload_file,
            file_data=content,
            filename=file.filename,
            content_type="model/gltf-binary",
            folder="web_models"
        )
        
        return {"code": 200, "url": url}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage Error: {str(e)}")

@router.get("/model/presigned-url", tags=["MinIO Storage"])
async def get_presigned_url(filename: str, content_type: str = "model/gltf-binary"):
    """
    [预签名上传] 获取上传 URL (推荐用于大文件上传)
    前端获取 URL 后，直接发起 PUT 请求上传文件。
    """
    try:
        result = minio_handler.get_presigned_upload_url(
            filename=filename,
            content_type=content_type,
            folder="web_models"
        )
        return {"code": 200, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Presign Error: {str(e)}")
```

### 3.5 注册路由 (`backend/main.py`)

```python
from api import api_data, api_topics, api_params, api_storage

# ...
app.include_router(api_storage.router, prefix="/api/v1", tags=["MinIO Storage"])
# ...
```

## 4. 植树调度系统具体应用场景

### 4.1 数字孪生模型管理 (Web 可视化)
*   **流程**：SolidWorks 导出 -> 后端 GLB 转换 -> MinIO (`web_models/`) -> 前端 Three.js 加载。
*   **优势**：前端直接通过 MinIO 返回的 URL 加载 2MB 左右的 GLB 文件，实现秒级打开，无需等待原生的 STL 解析。

### 4.2 机器人视觉监控
*   **流程**：机器人 ROS 节点 (CV Camera) -> 截图 -> Python SDK 上传 -> MinIO (`monitor/`) -> 调度大屏。
*   **扩展**：利用 MinIO 的生命周期管理功能，自动清理 30 天前的监控图片，节省磁盘空间。

### 4.3 远程日志归档
*   **流程**：机器人每日定时打包 `/var/log` -> MinIO (`logs/`)。
*   **价值**：当机器人出现故障时，研发人员无需 SSH 远程连接（可能无公网 IP），直接从管理后台下载 MinIO 中的日志包进行分析。

### 4.4 静态报表托管 (Freemarker 替代方案)
*   **流程**：后端定时任务生成“每日植树统计报告.html” -> MinIO (`reports/`)。
*   **价值**：利用 MinIO 作为静态资源服务器，减轻业务服务器的负载，管理者直接访问 HTML 链接查看报表。

## 5. 常见权限问题排查 (重要)

如果您在浏览器或前端代码中访问 MinIO 文件链接时，看到类似以下的 XML 错误：

```xml
<Error>
    <Code>AccessDenied</Code>
    <Message>Access Denied.</Message>
    ...
</Error>
```

**结论**：Bucket 仍为私有状态，前端**无法使用**。正常情况下浏览器应直接下载文件。

**原因**：MinIO 新版 Web 控制台移除了“修改权限”的入口，或者代码自动设置未生效。

**解决方案 (必做)**：
请直接在服务器终端执行以下 Docker 命令，使用 `mc` (MinIO Client) 强制开启公开下载权限：

```bash
# 1. 设置别名 (连接到本地 MinIO)
docker exec minio mc alias set local http://localhost:9000 admin TreeRobot_2026_Secure!

# 2. 开启匿名下载权限 (针对 tree-robot-assets 桶)
docker exec minio mc anonymous set download local/tree-robot-assets
```

**验证方法**：
再次刷新报错的 URL，如果浏览器开始下载文件，即表示修复成功。


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Any

import sys, os
# Ensure backend directory is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(".")

# 从 app_state 导入共享实例和回调所需的模块
from app_state import manager, data_source_manager

# --- 日志配置 ---
# 在应用启动最早期加载日志配置
from log_config import setup_logging
setup_logging()

# --- FastAPI 应用实例 ---
app = FastAPI(title="tStudio backend")

# --- 中间件 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 数据回调 ---
async def on_data_received(topic: str, data: Any):
    """数据接收回调, 广播给所有WebSocket客户端"""
    await manager.broadcast({
        "type": "data_update",
        "topic": topic,
        "data": data
    })

data_source_manager.add_data_callback(on_data_received)

# --- API路由 ---
# 导入并包含各个模块的路由
from api import api_data, api_topics, api_params
from modules.digital_twin import router as digital_twin_router
from core.db import init_db
from core.nacos_client import nacos_registry

app.include_router(api_data.router, prefix="/api", tags=["Data & Connection"])
app.include_router(api_topics.router, prefix="/api", tags=["Topics & WebSocket"])
app.include_router(api_params.router, prefix="/api/params", tags=["Parameters"])
app.include_router(digital_twin_router.router, prefix="/api", tags=["Digital Twin"])

# --- 健康检查 (兼容 Spring Boot Admin / Nacos) ---
@app.get("/actuator/health", tags=["Actuator"])
async def health_check():
    """兼容 Spring Boot Actuator 的健康检查接口，消除 Nacos/SBA 的 404 刷屏报错"""
    return {"status": "UP"}

@app.get("/actuator", tags=["Actuator"])
async def actuator_index():
    """兼容 Spring Boot Actuator 发现机制"""
    return {
        "_links": {
            "self": {"href": "/actuator", "templated": False},
            "health": {"href": "/actuator/health", "templated": False}
        }
    }

# --- 生命周期事件 ---
@app.on_event("startup")
async def on_startup():
    await init_db()
    # 注册到 Nacos
    nacos_registry.register()

@app.on_event("shutdown")
async def on_shutdown():
    # 从 Nacos 注销
    nacos_registry.deregister()

# --- 启动 ---
if __name__ == "__main__":
    import uvicorn
    # 注意这里的启动方式，对于uvicorn，它会找到app对象
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
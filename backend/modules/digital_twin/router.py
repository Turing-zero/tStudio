from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import Optional

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.db import SessionLocal, get_session
from .models import RobotModel
from .services import bake_zip_to_glb, cleanup_temp_dir
from services.storage import minio_handler

router = APIRouter()

def _clean_url(url: Optional[str]) -> Optional[str]:
    if url is None:
        return None
    u = str(url).strip()
    u = u.strip(" `\"'")
    return u or None


def _read_file_bytes(path: str) -> bytes:
    """
    读取本地文件内容的辅助函数（用于在线程池中运行同步IO）。
    """
    with open(path, "rb") as f:
        return f.read()


from app_state import manager

async def _process_robot_model(model_id: int, zip_path: str, activate: bool):
    """
    后台任务：处理上传的 Zip 包
    1. 解压并验证
    2. 转换 URDF -> GLB
    3. 上传到 MinIO
    4. 更新数据库状态
    """
    temp_root = None
    print(f"[DEBUG] Starting process for model {model_id}, zip: {zip_path}")
    try:
        async with SessionLocal() as session:
            result = await session.execute(select(RobotModel).where(RobotModel.id == model_id))
            model = result.scalar_one_or_none()
            if model is None:
                print(f"[DEBUG] Model {model_id} not found in DB")
                return

            # 注意：文件IO和MinIO上传通常是同步阻塞操作
            # 必须使用 run_in_threadpool 放入线程池执行，避免阻塞 FastAPI 的异步事件循环
            print(f"[DEBUG] Reading zip bytes...")
            zip_bytes = await run_in_threadpool(_read_file_bytes, zip_path)
            
            # 1. 上传原始 Zip 包
            print(f"[DEBUG] Uploading raw zip to MinIO...")
            source_zip_url = await run_in_threadpool(
                minio_handler.upload_file,
                file_data=zip_bytes,
                filename=os.path.basename(zip_path),
                content_type="application/zip",
                folder="raw_models",
            )
            print(f"[DEBUG] Zip uploaded: {source_zip_url}")

            # 2. 调用转换服务 (CPU密集型/IO密集型混合)
            print(f"[DEBUG] Baking zip to GLB...")
            temp_root, urdf_path, glb_path = await run_in_threadpool(bake_zip_to_glb, zip_path)
            print(f"[DEBUG] Bake finished. GLB: {glb_path}")

            urdf_bytes = await run_in_threadpool(_read_file_bytes, urdf_path)
            glb_bytes = await run_in_threadpool(_read_file_bytes, glb_path)

            print(f"[DEBUG] Uploading assets to MinIO...")
            urdf_url = await run_in_threadpool(
                minio_handler.upload_file,
                file_data=urdf_bytes,
                filename=os.path.basename(urdf_path),
                content_type="application/xml",
                folder="raw_models",
            )
            glb_url = await run_in_threadpool(
                minio_handler.upload_file,
                file_data=glb_bytes,
                filename=os.path.basename(glb_path),
                content_type="model/gltf-binary",
                folder="web_models",
            )
            print(f"[DEBUG] Assets uploaded. GLB URL: {glb_url}")

            model.source_zip_url = source_zip_url
            model.urdf_url = urdf_url
            model.display_model_url = glb_url
            model.status = "ready"
            model.error_message = None
            model.updated_at = datetime.utcnow()

            # 4. 如果请求要求激活，则处理互斥逻辑
            if activate:
                # 将同类型的其他模型设为非激活状态
                others_result = await session.execute(
                    select(RobotModel).where(
                        RobotModel.robot_type == model.robot_type,
                        RobotModel.is_active == True,
                        RobotModel.id != model.id,
                    )
                )
                for other in others_result.scalars().all():
                    other.is_active = False
                    other.updated_at = datetime.utcnow()
                
                # 激活当前模型
                model.is_active = True

            await session.commit()
            
            # 5. 广播 WebSocket 事件 (仅当激活时)
            if activate:
                await manager.broadcast({
                    "type": "MODEL_UPDATED",
                    "payload": {
                        "robot_type": model.robot_type,
                        "version": model.version,
                        "url": model.display_model_url
                    }
                })

    except Exception as e:
        print(f"[ERROR] Process failed: {e}")
        async with SessionLocal() as session:
            result = await session.execute(select(RobotModel).where(RobotModel.id == model_id))
            model = result.scalar_one_or_none()
            if model is not None:
                model.status = "failed"
                model.error_message = str(e)
                model.updated_at = datetime.utcnow()
                await session.commit()
    finally:
        if temp_root is not None:
            await run_in_threadpool(cleanup_temp_dir, temp_root)
        await run_in_threadpool(lambda: os.path.exists(zip_path) and os.remove(zip_path))


@router.post("/model/upload-zip", tags=["Digital Twin"])
async def upload_robot_model_zip(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    version: str = Form(...),
    robot_type: str = Form("tree_planter"),
    activate: bool = Form(True),
    session: AsyncSession = Depends(get_session),
):
    """
    上传机器人模型压缩包 (Zip)。
    
    - 接收 Zip 文件（包含 URDF 及相关资源）。
    - 在数据库创建记录 (状态: processing)。
    - 启动后台任务进行模型转换和 MinIO 上传。
    """
    suffix = os.path.splitext(file.filename or "")[1] or ".zip"
    fd, temp_path = tempfile.mkstemp(prefix="tstudio_upload_", suffix=suffix)
    os.close(fd)

    try:
        # 使用流式写入将上传的文件保存到临时目录，避免大文件占用过多内存
        async with aiofiles.open(temp_path, "wb") as f:
            while True:
                # 每次读取 1MB
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                await f.write(chunk)

        # 先在数据库创建记录，获取 ID，状态标记为 processing
        model = RobotModel(version=version, robot_type=robot_type, status="processing", is_active=False)
        session.add(model)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status_code=409, detail="version already exists")
        await session.refresh(model)

        # 启动后台任务进行耗时的转换和上传操作
        background_tasks.add_task(_process_robot_model, model.id, temp_path, activate)
        return {"id": model.id, "version": model.version, "status": model.status}

    except HTTPException:
        await run_in_threadpool(lambda: os.path.exists(temp_path) and os.remove(temp_path))
        raise
    except Exception as e:
        await run_in_threadpool(lambda: os.path.exists(temp_path) and os.remove(temp_path))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model/latest", tags=["Digital Twin"])
async def get_latest_active_model(
    robot_type: str = "tree_planter",
    session: AsyncSession = Depends(get_session),
):
    """
    获取当前激活的最新机器人模型。
    
    用于前端展示当前生效的数字孪生模型。
    """
    result = await session.execute(
        select(RobotModel)
        .where(
            RobotModel.robot_type == robot_type,
            RobotModel.is_active == True,
            RobotModel.status == "ready",
        )
        .order_by(RobotModel.created_at.desc())
        .limit(1)
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="active model not found")
    data = model.model_dump()
    data["source_zip_url"] = _clean_url(data.get("source_zip_url"))
    data["urdf_url"] = _clean_url(data.get("urdf_url"))
    data["display_model_url"] = _clean_url(data.get("display_model_url"))
    data["preview_url"] = _clean_url(data.get("preview_url"))
    return data


@router.get("/models", tags=["Digital Twin"])
async def list_models(
    robot_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """
    分页查询机器人模型列表。
    
    支持按 robot_type 和 status 过滤。
    """
    query = select(RobotModel).order_by(RobotModel.created_at.desc()).offset(offset).limit(limit)
    if robot_type:
        query = query.where(RobotModel.robot_type == robot_type)
    if status:
        query = query.where(RobotModel.status == status)
    result = await session.execute(query)
    return result.scalars().all()


@router.post("/models/{model_id}/activate", tags=["Digital Twin"])
async def activate_model(
    model_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(RobotModel).where(RobotModel.id == model_id))
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    if model.status != "ready":
        raise HTTPException(status_code=409, detail="model not ready")

    # 1. 查找同类型当前已激活的其他模型
    others_result = await session.execute(
        select(RobotModel).where(RobotModel.robot_type == model.robot_type, RobotModel.is_active == True)
    )
    # 2. 停用它们
    for other in others_result.scalars().all():
        other.is_active = False
        other.updated_at = datetime.utcnow()

    # 3. 激活目标模型
    model.is_active = True
    model.updated_at = datetime.utcnow()
    
    await session.commit()
    await session.refresh(model)
    return model

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from services.storage import minio_handler

router = APIRouter()

@router.post("/model/upload", tags=["MinIO Storage"])
async def upload_robot_model(file: UploadFile = File(...)):
    """
    [代理上传] 处理 GLB 模型上传 (通常由转换管线调用)
    注意：MinIO SDK 是同步的，必须使用 run_in_threadpool 避免阻塞 Event Loop
    """
    try:
        # 1. 异步读取文件内容 (FastAPI UploadFile.read 是异步的)
        content = await file.read()
        
        # 2. 在线程池中执行同步上传操作
        # 注意：现在 minio_handler 是 StorageAdapter 的实现类 MinioAdapter
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

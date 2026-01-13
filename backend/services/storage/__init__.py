from .adapter import StorageAdapter
from .minio_impl import MinioAdapter, minio_handler

# 导出所有关键组件
__all__ = ["StorageAdapter", "MinioAdapter", "minio_handler"]

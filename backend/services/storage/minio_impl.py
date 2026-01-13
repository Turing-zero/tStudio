from minio import Minio
from minio.error import S3Error
from datetime import datetime, timedelta
import io
import json
import uuid
from typing import Union, BinaryIO, List, Dict
from core.env_config import settings
from .adapter import StorageAdapter

class MinioAdapter(StorageAdapter):
    """MinIO 对象存储实现"""
    
    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """初始化时检查 Bucket，不存在则自动创建，并强制设置 Public Policy"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
            
            # 强制设置 Bucket 策略为 Public Read (即使 Bucket 已存在)
            # 这样可以修复手动创建 Bucket 忘记设 Policy 的情况
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{self.bucket_name}/*"]
                    }
                ]
            }
            self.client.set_bucket_policy(self.bucket_name, json.dumps(policy))
        except Exception as e:
            print(f"Error checking/setting bucket policy: {e}")

    def _get_object_name(self, folder: str, filename: str) -> str:
        date_prefix = datetime.now().strftime("%Y/%m/%d")
        # Add short UUID to prevent overwriting same filename
        unique_id = str(uuid.uuid4())[:8]
        return f"{folder}/{date_prefix}/{unique_id}_{filename}"

    def upload_file(self, file_data: Union[bytes, BinaryIO], filename: str, content_type: str, folder: str = "misc") -> str:
        object_name = self._get_object_name(folder, filename)
        
        if isinstance(file_data, bytes):
            data_stream = io.BytesIO(file_data)
            length = len(file_data)
        else:
            data_stream = file_data
            # Try to get length if possible, otherwise read into memory (not ideal for huge files but safe)
            try:
                length = data_stream.getbuffer().nbytes
            except AttributeError:
                content = data_stream.read()
                data_stream = io.BytesIO(content)
                length = len(content)

        self.client.put_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            data=data_stream,
            length=length,
            content_type=content_type
        )
        
        protocol = "https" if settings.MINIO_SECURE else "http"
        return f"{protocol}://{settings.MINIO_ENDPOINT}/{self.bucket_name}/{object_name}"

    def download_file(self, object_name: str) -> bytes:
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            return response.read()
        finally:
            if 'response' in locals():
                response.close()
                
    def delete_file(self, object_name: str) -> bool:
        try:
            self.client.remove_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False

    def file_exists(self, object_name: str) -> bool:
        try:
            self.client.stat_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False

    def list_files(self, prefix: str = "", recursive: bool = True) -> List[Dict]:
        objects = self.client.list_objects(self.bucket_name, prefix=prefix, recursive=recursive)
        return [
            {
                "object_name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified
            }
            for obj in objects
        ]

    def get_presigned_upload_url(self, filename: str, content_type: str, folder: str = "web_models") -> dict:
        object_name = self._get_object_name(folder, filename)
        
        url = self.client.presigned_put_object(
            self.bucket_name,
            object_name,
            expires=timedelta(hours=1)
        )
        
        protocol = "https" if settings.MINIO_SECURE else "http"
        access_url = f"{protocol}://{settings.MINIO_ENDPOINT}/{self.bucket_name}/{object_name}"
        
        return {
            "upload_url": url,
            "access_url": access_url,
            "object_name": object_name
        }

    def get_presigned_download_url(self, object_name: str, expires_hours: int = 1) -> str:
        return self.client.presigned_get_object(
            self.bucket_name,
            object_name,
            expires=timedelta(hours=expires_hours)
        )

# 单例导出 (依赖注入风格)
minio_handler = MinioAdapter()

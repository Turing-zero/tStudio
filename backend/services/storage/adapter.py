from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Union, BinaryIO

class StorageAdapter(ABC):
    """
    通用对象存储适配器接口
    任何云存储服务（MinIO, OSS, S3, BOS）都应实现此接口
    """

    @abstractmethod
    def upload_file(self, file_data: Union[bytes, BinaryIO], filename: str, content_type: str, folder: str) -> str:
        """上传文件并返回访问 URL"""
        pass

    @abstractmethod
    def download_file(self, object_name: str) -> bytes:
        """下载文件内容"""
        pass

    @abstractmethod
    def delete_file(self, object_name: str) -> bool:
        """删除文件"""
        pass

    @abstractmethod
    def file_exists(self, object_name: str) -> bool:
        """检查文件是否存在"""
        pass

    @abstractmethod
    def list_files(self, prefix: str = "", recursive: bool = True) -> List[Dict]:
        """列出文件列表"""
        pass

    @abstractmethod
    def get_presigned_upload_url(self, filename: str, content_type: str, folder: str) -> dict:
        """获取预签名上传 URL"""
        pass

    @abstractmethod
    def get_presigned_download_url(self, object_name: str, expires_hours: int = 1) -> str:
        """获取预签名下载/访问 URL"""
        pass

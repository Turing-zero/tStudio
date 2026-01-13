import os
import sys

# 添加 backend 目录到 path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.env_config import settings
from services.storage.minio_impl import minio_handler

print(f"MINIO_ENDPOINT raw: '{settings.MINIO_ENDPOINT}'")
print(f"MINIO_ENDPOINT repr: {repr(settings.MINIO_ENDPOINT)}")

url = minio_handler.upload_file(
    file_data=b"test",
    filename="test.txt",
    content_type="text/plain",
    folder="debug"
)

print(f"Generated URL raw: '{url}'")
print(f"Generated URL repr: {repr(url)}")

# Check env var directly
print(f"Env MINIO_ENDPOINT: {repr(os.environ.get('MINIO_ENDPOINT'))}")

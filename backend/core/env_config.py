from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # MinIO 配置
    MINIO_ENDPOINT: str = "10.144.144.2:9000"      # 注意：不要带 http://
    MINIO_ACCESS_KEY: str = "admin"             # 对应 MINIO_ROOT_USER
    MINIO_SECRET_KEY: str = "TreeRobot_2026_Secure!" # 对应 MINIO_ROOT_PASSWORD
    MINIO_BUCKET_NAME: str = "tree-robot-assets"
    MINIO_SECURE: bool = False                  # 内网部署通常为 False (HTTP)
    # todo 此处需要在数据库新建表 tstudio，否则会报错
    DATABASE_URL: str = "mysql+aiomysql://root:1234@127.0.0.1:3306/tstudio?charset=utf8mb4"
    DATABASE_ECHO: bool = False

    class Config:
        import os
        
        # 1. 获取运行环境标识 (默认 dev)
        # 使用方式: set APP_ENV=prod && python main.py
        _app_env = os.getenv("APP_ENV", "dev").lower()
        
        # 2. 确定配置文件名
        # dev -> .env
        # test -> .env.test
        # prod -> .env.prod
        _env_filename = ".env" if _app_env == "dev" else f".env.{_app_env}"
        
        # 3. 构造绝对路径
        _base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_file = os.path.join(_base_dir, _env_filename)
        
        env_file_encoding = "utf-8"

settings = Settings()

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class RobotModel(SQLModel, table=True):
    """
    数字孪生机器人模型实体。
    
    存储机器人 3D 模型的元数据、文件存储路径以及处理状态。
    该表记录了从原始 Zip 包到 Web 可视化格式 (GLB) 的转换过程。
    """
    id: Optional[int] = Field(default=None, primary_key=True, description="主键 ID")
    
    # 业务标识
    version: str = Field(index=True, unique=True, description="模型语义化版本号 (如 v1.0.0)")
    robot_type: str = Field(default="turtlebot3", index=True, description="机器人类型标识 (用于区分不同机型)")

    # 资源存储路径 (MinIO URL)
    source_zip_url: Optional[str] = Field(default=None, description="原始上传的 Zip 包下载链接")
    urdf_url: Optional[str] = Field(default=None, description="解压后的主 URDF 文件链接")
    display_model_url: Optional[str] = Field(default=None, description="转换后的 Web 友好格式 (GLB) 链接")
    preview_url: Optional[str] = Field(default=None, description="模型缩略图链接 (可选)")

    # 状态管理
    status: str = Field(default="processing", index=True, description="处理状态: processing, ready, failed")
    error_message: Optional[str] = Field(default=None, description="处理失败时的错误详情")

    # 版本控制
    is_active: bool = Field(default=False, index=True, description="是否为当前生效的激活版本")
    
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True, description="更新时间")

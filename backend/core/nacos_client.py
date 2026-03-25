import socket
import logging
from nacos import NacosClient
from core.env_config import settings

logger = logging.getLogger(__name__)

class NacosRegistry:
    def __init__(self):
        self.client = None
        self.service_name = settings.NACOS_SERVICE_NAME
        self.port = settings.NACOS_SERVICE_PORT
        self.ip = self._get_local_ip()
        
    def _get_local_ip(self):
        """获取本机IP地址"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # 并不需要实际连接，只是为了探测IP
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def register(self):
        """注册服务到 Nacos"""
        if not settings.ENABLE_NACOS_DISCOVERY:
            logger.info("Nacos discovery is disabled.")
            return

        try:
            logger.info(f"Connecting to Nacos server: {settings.NACOS_SERVER_ADDR}")
            self.client = NacosClient(
                server_addresses=settings.NACOS_SERVER_ADDR,
                namespace=settings.NACOS_NAMESPACE,
                username=settings.NACOS_USERNAME,
                password=settings.NACOS_PASSWORD
            )
            
            logger.info(f"Registering service {self.service_name} at {self.ip}:{self.port}")
            self.client.add_naming_instance(
                self.service_name,
                self.ip,
                self.port,
                cluster_name="DEFAULT",
                group_name="DEFAULT_GROUP",
                metadata={"preserved.register.source": "PYTHON-FASTAPI"},
                heartbeat_interval=5
            )
            logger.info("Successfully registered to Nacos.")
        except Exception as e:
            logger.error(f"Failed to register to Nacos: {e}")

    def deregister(self):
        """从 Nacos 注销服务"""
        if not self.client:
            return

        try:
            logger.info(f"Deregistering service {self.service_name}")
            self.client.remove_naming_instance(
                self.service_name,
                self.ip,
                self.port,
                cluster_name="DEFAULT",
                group_name="DEFAULT_GROUP"
            )
            logger.info("Successfully deregistered from Nacos.")
        except Exception as e:
            logger.error(f"Failed to deregister from Nacos: {e}")

nacos_registry = NacosRegistry()

import os
import logging
import logging.config
import sys
from pythonjsonlogger import jsonlogger

# --- Future-Proofing: ContextVar for Trace IDs ---
# 在未来接入 SkyWalking 或 Spring Cloud Sleuth 时，
# 我们将使用 contextvars 在中间件中存储 Trace ID。
# 这里预留 Filter 位置。
class TraceIdFilter(logging.Filter):
    def filter(self, record):
        # TODO: 未来从 contextvars 获取 trace_id
        # record.trace_id = context.get_trace_id() or "N/A"
        return True

def setup_logging():
    """
    初始化日志配置
    根据环境变量 ENV 决定使用 JSON (PROD) 还是 Text (DEV) 格式
    """
    env = os.getenv("ENV", "DEV").upper()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # 1. 定义格式器
    formatters = {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            # JSON 模式下，我们希望字段更丰富，方便 ELK 索引
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(lineno)d %(filename)s",
        },
    }

    # 2. 决定当前环境使用的格式器
    # 如果是 PROD 环境，强制使用 json，否则使用 standard
    # 你也可以通过环境变量 LOG_FORMAT=json 来强制覆盖
    requested_format = os.getenv("LOG_FORMAT", "json" if env == "PROD" else "standard")
    if requested_format not in formatters:
        requested_format = "standard"

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,  # 关键：不要禁用 Uvicorn 等第三方库的日志
        "filters": {
            "trace_id": {
                "()": TraceIdFilter
            }
        },
        "formatters": formatters,
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": requested_format,
                "stream": "ext://sys.stdout",
                "filters": ["trace_id"],
            },
        },
        "loggers": {
            # Root Logger: 捕获所有未被专门配置的日志
            "": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": True,
            },
            # Uvicorn Access Log: 调整为我们的格式
            "uvicorn.access": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            # Uvicorn Error Log
            "uvicorn.error": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            # 我们的应用日志
            "backend": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(logging_config)
    
    # 打印一条初始化日志，确认配置生效
    logger = logging.getLogger("backend.core")
    logger.info(f"Logging configured. Environment: {env}, Level: {log_level}, Format: {requested_format}")

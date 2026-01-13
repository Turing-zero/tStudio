import time
import os
import sys
import shutil
import hashlib
import argparse
import logging
from threading import Timer
from typing import Optional

import requests
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('model_watcher.log')
    ]
)
logger = logging.getLogger(__name__)

class RobotModelPusher(FileSystemEventHandler):
    def __init__(self, api_url: str, watch_dir: str, robot_type: str = "tree_planter"):
        self.api_url = api_url
        self.watch_dir = os.path.abspath(watch_dir)
        self.robot_type = robot_type
        self.timer: Optional[Timer] = None
        self.last_md5 = self._calculate_directory_hash()
        
        # 配置重试策略
        self.max_retries = 5
        self.base_delay = 2  # 基础延迟 2秒
        
        logger.info(f"Watcher initialized.")
        logger.info(f"  - Target Dir: {self.watch_dir}")
        logger.info(f"  - API URL:    {self.api_url}")
        logger.info(f"  - Robot Type: {self.robot_type}")
        logger.info(f"  - Initial MD5: {self.last_md5}")

        # 启动定期同步任务 (每1小时执行一次)
        self._start_periodic_sync(interval=3600)

    def _start_periodic_sync(self, interval: int):
        """启动定期全量同步的后台定时器"""
        def sync_task():
            logger.info("[Periodic Sync] Starting hourly consistency check...")
            try:
                # 强制触发一次检查逻辑
                self.execute_push(force_check=True)
            except Exception as e:
                logger.error(f"[Periodic Sync] Error: {e}")
            finally:
                # 重新调度下一次
                self._sync_timer = Timer(interval, sync_task)
                self._sync_timer.daemon = True
                self._sync_timer.start()

        self._sync_timer = Timer(interval, sync_task)
        self._sync_timer.daemon = True
        self._sync_timer.start()
        logger.info(f"Periodic sync scheduled (Interval: {interval}s)")

    def _calculate_directory_hash(self) -> str:
        """
        计算目录下所有相关文件 (urdf, stl, dae) 的内容 MD5 指纹。
        用于避免无效上传。
        """
        hash_md5 = hashlib.md5()
        file_paths = []
        
        # 遍历目录，收集所有文件路径
        for root, dirs, files in os.walk(self.watch_dir):
            # 排序以确保顺序一致
            dirs.sort()
            for file in sorted(files):
                if file.lower().endswith(('.urdf', '.stl', '.dae', '.xml', '.xacro')):
                    file_paths.append(os.path.join(root, file))
        
        # 按路径顺序读取文件内容更新哈希
        for file_path in file_paths:
            try:
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
            except Exception as e:
                logger.warning(f"Failed to read file for hashing: {file_path}, error: {e}")
                
        return hash_md5.hexdigest()

    def on_modified(self, event):
        if event.is_directory:
            return
        
        # 简单过滤，只响应相关文件
        if not event.src_path.lower().endswith(('.urdf', '.stl', '.dae', '.xml', '.xacro')):
            return

        logger.info(f"Detected change: {event.src_path}")
        
        # 防抖逻辑：如果有正在等待的定时器，取消它
        if self.timer:
            self.timer.cancel()
        
        # 设置新的定时器，2秒后触发上传
        self.timer = Timer(2.0, self.execute_push)
        self.timer.start()

    def on_created(self, event):
        self.on_modified(event)

    def on_deleted(self, event):
        self.on_modified(event)

    def execute_push(self, force_check: bool = False):
        """执行打包和上传逻辑 (包含重试机制)"""
        logger.info("Debounce finished. Checking content...")
        
        # 1. 再次计算指纹，对比是否真的有内容变化
        current_md5 = self._calculate_directory_hash()
        
        # 如果指纹未变且不是强制检查，则跳过
        if current_md5 == self.last_md5 and not force_check:
            logger.info("Content MD5 unchanged. Skipping upload.")
            return
            
        # 如果是强制检查但指纹没变，记录一下日志（可选：也可以选择不上报，取决于业务需求）
        # 这里策略是：如果 Periodic Sync 发现指纹一致，通常不需要上传，除非为了 heartbeat
        # 但为了简化，我们假设指纹一致就不上传。
        if force_check and current_md5 == self.last_md5:
            logger.info("[Periodic Sync] Content consistent with last success. No upload needed.")
            return

        logger.info(f"Content update required (MD5: {current_md5}). Preparing upload...")
        
        temp_zip_base = os.path.join(os.path.dirname(self.watch_dir), "temp_robot_model")
        zip_filename = f"{temp_zip_base}.zip"
        
        try:
            # 2. 打包 ZIP
            shutil.make_archive(temp_zip_base, 'zip', root_dir=self.watch_dir)
            logger.info(f"Created archive: {zip_filename}")
            
            # 3. 上传 (带重试机制)
            self._upload_with_retry(zip_filename, current_md5)
                    
        except Exception as e:
            logger.error(f"Error during push process: {e}", exc_info=True)
        finally:
            # 清理临时文件
            if os.path.exists(zip_filename):
                try:
                    os.remove(zip_filename)
                except OSError:
                    pass

    def _upload_with_retry(self, zip_filename: str, current_md5: str):
        """带有指数退避的上传逻辑"""
        version_tag = f"auto-{int(time.time())}"
        
        for attempt in range(1, self.max_retries + 1):
            try:
                with open(zip_filename, 'rb') as f:
                    files = {'file': (f"model_{version_tag}.zip", f, 'application/zip')}
                    data = {
                        'version': version_tag,
                        'robot_type': self.robot_type,
                        'activate': 'true'
                    }
                    
                    logger.info(f"[Attempt {attempt}/{self.max_retries}] Uploading to {self.api_url}...")
                    response = requests.post(self.api_url, files=files, data=data, timeout=30)
                    
                    if response.status_code == 200:
                        logger.info(f"Upload SUCCESS! Server response: {response.json()}")
                        self.last_md5 = current_md5  # 更新指纹
                        return # 成功退出
                    else:
                        logger.warning(f"Upload failed with status {response.status_code}: {response.text}")
                        # 4xx 错误通常是客户端问题（如校验失败），重试可能无意义，这里选择继续重试还是中断视情况而定
                        # 假设 5xx 或 网络错误才需要重试
                        if 400 <= response.status_code < 500:
                             logger.error("Client error (4xx), stopping retries.")
                             return

            except requests.RequestException as e:
                logger.warning(f"Network error during upload: {e}")
            
            # 计算下一次重试的等待时间 (指数退避)
            if attempt < self.max_retries:
                delay = self.base_delay * (2 ** (attempt - 1))
                logger.info(f"Waiting {delay} seconds before next retry...")
                time.sleep(delay)
        
        logger.error(f"All {self.max_retries} attempts failed. Will retry on next file change or sync cycle.")

def main():
    parser = argparse.ArgumentParser(description="Robot Model Watcher & Auto-Syncer")
    parser.add_argument("--dir", required=True, help="Directory to watch (e.g., ./src/tree_robot_description)")
    parser.add_argument("--url", default="http://localhost:3500/api/model/upload-zip", help="Server API URL")
    parser.add_argument("--type", default="tree_planter", help="Robot Type Identifier")
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.dir):
        logger.error(f"Error: Directory '{args.dir}' does not exist.")
        sys.exit(1)

    event_handler = RobotModelPusher(args.url, args.dir, args.type)
    observer = Observer()
    observer.schedule(event_handler, args.dir, recursive=True)
    
    observer.start()
    logger.info(f"Monitoring started on {args.dir}. Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Stopping watcher...")
    
    observer.join()

if __name__ == "__main__":
    main()

import logging
import logging.handlers
import queue
import threading
import time
import json
import sys
import requests
import abc
import copy
import functools
import string
from typing import Any, Dict, Optional, Tuple, List

from loguru import logger, Record




# --- 配置 (Config) ---
class LokiConfig:
    """Loki 日志上传器的配置常量"""
    SUCCESS_RESPONSE_CODE: int = 204
    LEVEL_TAG: str = "severity"
    LOGGER_TAG: str = "logger"
    # Loki URL, 请替换为你的 Loki push 端点
    LOG_UPLOAD_URL = "http://127.0.0.1:3100/loki/api/v1/push"
    LOG_BATCH_SIZE = 100  # 每次批量上传的最大日志条数
    LOG_UPLOAD_TIMEOUT = 10  # 最大上传间隔（秒）

    # 标签格式化常量
    LABEL_ALLOWED_CHARS: str = "".join((string.ascii_letters, string.digits, "_"))
    LABEL_REPLACE_WITH: Tuple[Tuple[str, str], ...] = (
        ("'", ""), ('"', ""), (" ", "_"), (".", "_"), ("-", "_"),
    )
    FORMAT_LABEL_LRU_SIZE: int = 256


BasicAuth = Optional[Tuple[str, str]]


# --- Emitter 基类 (负责 Loki Payload 格式化) ---
class LokiEmitter(abc.ABC):
    """用于发送日志条目的 Loki 基础发射器类，负责格式化和 HTTP 客户端管理。"""

    def __init__(self, url: str, tags: Optional[dict] = None, auth: BasicAuth = None):
        self.url = url
        self.tags = tags if tags is not None else {}
        self.auth = auth
        # 使用 requests.Session() 实现连接复用，提高性能
        self._session = requests.Session()
        if auth:
            self._session.auth = auth
        self.client = self._session

    @functools.lru_cache(LokiConfig.FORMAT_LABEL_LRU_SIZE)
    def format_label(self, label: str) -> str:
        """格式化标签以匹配 Prometheus/Loki 要求。"""
        label = str(label)
        for char_from, char_to in LokiConfig.LABEL_REPLACE_WITH:
            label = label.replace(char_from, char_to)
        return "".join(char for char in label if char in LokiConfig.LABEL_ALLOWED_CHARS)

    def build_tags(self, record: logging.LogRecord) -> Dict[str, Any]:
        """返回要与日志记录一起发送到 Loki 的标签。"""
        tags = copy.deepcopy(self.tags)
        tags[LokiConfig.LEVEL_TAG] = record.levelname.lower()
        tags[LokiConfig.LOGGER_TAG] = record.name

        # 从 record.extra 中获取额外标签
        extra_tags = getattr(record, "tags", {})
        if isinstance(extra_tags, dict):
            for tag_name, tag_value in extra_tags.items():
                cleared_name = self.format_label(tag_name)
                if cleared_name:
                    # 确保标签值为字符串
                    tags[cleared_name] = str(tag_value)
        return tags

    def build_tags_from_loguru(self, record: "Record") -> Dict[str, Any]:
        """从 loguru 记录构建标签"""
        tags = copy.deepcopy(self.tags)
        tags[LokiConfig.LEVEL_TAG] = record["level"].name.lower()
        tags[LokiConfig.LOGGER_TAG] = record["name"]

        # 从 extra 中获取额外标签
        extra_tags = record.get("extra", {})
        if isinstance(extra_tags, dict):
            for tag_name, tag_value in extra_tags.items():
                cleared_name = self.format_label(tag_name)
                if cleared_name:
                    # 确保标签值为字符串
                    tags[cleared_name] = str(tag_value)
        return tags

    def build_payload(self, records: list) -> dict:
        """为日志条目构建 JSON 有效负载，按标签分组为 streams。"""
        streams = {}
        ns = 1e9  # 纳秒转换

        for record in records:
            # 处理不同的日志记录类型
            if isinstance(record, logging.LogRecord):
                # 标准 logging 记录
                labels_dict = self.build_tags(record)
                message = record.getMessage()
                timestamp = str(int(record.created * ns))
            elif isinstance(record, dict) and logger is not None:
                # Loguru 记录
                labels_dict = self.build_tags_from_loguru(record)
                message = record["message"]
                timestamp = str(int(record["time"].timestamp() * ns))
            else:
                continue

            labels_key = tuple(sorted(labels_dict.items()))
            
            if labels_key not in streams:
                streams[labels_key] = {
                    "stream": labels_dict,
                    "values": []
                }
            streams[labels_key]["values"].append([timestamp, message])

        return {"streams": list(streams.values())}

    def close(self):
        """关闭 HTTP 客户端会话。"""
        if self._session is not None:
            self._session.close()
            self._session = None
            print("LokiEmitter: HTTP 会话已关闭。")


# --- LogUploaderThread (负责异步上传和批次管理) ---
class LogUploaderThread(threading.Thread, LokiEmitter):
    """
    负责从队列中消费日志，按批次或时间间隔上传到 Loki 的线程。
    使用 threading.Event 确保优雅关闭。
    """

    def __init__(self, log_queue: queue.Queue, upload_url: str, tags: Optional[dict] = None, auth: BasicAuth = None):
        threading.Thread.__init__(self, name="LokiUploaderThread")
        LokiEmitter.__init__(self, upload_url, tags, auth)

        self.queue = log_queue
        self.batch: List[logging.LogRecord] = []
        self.last_upload_time = time.time()
        # 使用 Event 进行优雅关闭
        self._stop_event = threading.Event()

        print(f"LokiUploaderThread 已启动。上传 URL: {self.url}")

    def upload_logs(self):
        """执行实际的 HTTP POST 上传。"""
        if not self.batch: return

        # 复制批次以防止在上传过程中有新日志进入
        batch_to_upload = list(self.batch)
        self.batch.clear()

        try:
            payload = self.build_payload(batch_to_upload)
            if not payload["streams"]: return

            json_payload = json.dumps(payload)
            headers = {"Content-Type": "application/json"}

            print(f"--- [Loki 批量上传] ---")
            print(f"准备上传 {len(batch_to_upload)} 条日志 (分为 {len(payload['streams'])} 个流) 到 {self.url}")

            response = self.client.post(
                self.url,
                data=json_payload,
                headers=headers,
                timeout=10
            )

            if response.status_code == LokiConfig.SUCCESS_RESPONSE_CODE:
                print(f"上传成功。服务器响应: {response.status_code}")
            else:
                # 如果失败，则打印错误日志，但不重新放入队列，以防持续失败
                response.raise_for_status()

        except requests.exceptions.RequestException as e:
            # 直接打印到 stderr，避免日志循环
            print(f"[错误] Loki 日志上传失败 ({len(batch_to_upload)} 条日志丢失): {e}", file=sys.stderr)
            if hasattr(e, 'response') and e.response is not None:
                print(f"服务器响应内容: {e.response.text}", file=sys.stderr)
        except Exception as e:
            print(f"[错误] 构建 Loki payload 或序列化时失败: {e}", file=sys.stderr)
        finally:
            print(f"--- [上传结束] ---")

    def run(self):
        """线程主循环，从队列中消费日志并管理上传批次。"""
        print(f"LokiUploaderThread: 线程主循环开始运行...")

        while not self._stop_event.is_set():
            try:
                # 设置 timeout，让线程有机会检查 _stop_event
                record = self.queue.get(timeout=1)
                self.batch.append(record)

                # 检查是否达到批次大小限制
                if len(self.batch) >= LokiConfig.LOG_BATCH_SIZE:
                    self.upload_logs()
                    self.last_upload_time = time.time()  # 达到批次时重置定时器

            except queue.Empty:
                # 队列为空或等待超时，检查是否达到时间限制
                if (time.time() - self.last_upload_time) >= LokiConfig.LOG_UPLOAD_TIMEOUT:
                    self.upload_logs()
                    self.last_upload_time = time.time()  # 达到时间限制时重置定时器

            except Exception as e:
                # 捕获其他运行时异常，避免线程崩溃
                print(f"[致命错误] Loki 上传线程发生意外错误: {e}", file=sys.stderr)
                time.sleep(1)  # 避免在错误中进入忙循环

        # 优雅关闭：退出循环前，执行最后一次日志上传
        if self.batch:
            print(f"LokiUploaderThread: 收到停止信号。正在上传最后 {len(self.batch)} 条日志...")
            self.upload_logs()

        self.close()  # 关闭 HTTP Session
        print("LokiUploaderThread: 线程已退出。")


# --- LokiQueueHandler (新的入口，隐藏队列) ---
class LokiQueueHandler(logging.handlers.QueueHandler):
    """
    一个集成 Loki 异步上传线程的 QueueHandler。
    它负责创建队列、启动上传线程，并在关闭时进行优雅停止。
    """
    # 明确声明 queue 的类型，以解决 type checker 警告
    queue: queue.Queue

    def __init__(self, upload_url: str, tags: Optional[dict] = None, auth: BasicAuth = None):
        # 1. 内部创建队列
        log_queue = queue.Queue(-1)  # 无限大小的队列
        super().__init__(log_queue)

        # 2. 创建并启动上传线程
        self.uploader_thread = LogUploaderThread(
            log_queue,
            upload_url=upload_url,
            tags=tags,
            auth=auth
        )
        self.uploader_thread.start()

    def stop(self):
        """
        优雅地停止上传线程并清理队列。
        """
        if self.uploader_thread:
            self.uploader_thread.stop()

        # 清空队列，防止主程序退出时仍有 LogRecord 导致异常
        while not self.queue.empty():
            try:
                # 使用 self.queue 访问父类 QueueHandler 的内部队列
                self.queue.get_nowait()
            except queue.Empty:
                break

        print("LokiQueueHandler: 已安全停止日志上传服务。")

    def write(self, message):
        """
        使 LokiQueueHandler 可以作为 loguru 的 sink
        """
        # 创建一个简单的记录对象来传递给队列
        record = {
            "message": message,
            "level": {"name": "INFO"},
            "name": "loguru",
            "time": time.time(),
            "extra": {}
        }
        self.queue.put(record)


# --- 日志配置 ---
def setup_logging(loki_handler: LokiQueueHandler):
    """
    配置根日志记录器，添加控制台 Handler 和 LokiQueueHandler。
    """
    # 1. 控制台 Handler
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(threadName)s)'
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 确保没有重复的 Handler
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(console_handler)  # 日志同时发往控制台
    root_logger.addHandler(loki_handler)  # 日志同时发往 Loki 异步队列


# --- 主应用程序 ---
if __name__ == "__main__":

    # 1. 配置 Loki 参数
    # 定义将附加到 *所有* 日志的全局标签
    global_loki_tags = {
        "app": "async-uploader-demo-optimized",
        "env": "production"
    }

    # 如果您的 Loki 需要基本认证: ("username", "password")
    loki_auth = None

    # 2. 创建 Loki Handler (同时创建并启动了内部上传线程)
    # log_queue 现在被封装在 loki_handler 内部，不再暴露给主程序
    loki_uploader_handler = LokiQueueHandler(
        upload_url=LokiConfig.LOG_UPLOAD_URL,
        tags=global_loki_tags,
        auth=loki_auth
    )

    # 3. 配置日志系统，将 Handler 添加到 Root Logger
    setup_logging(loki_uploader_handler)

    logging.info("主应用程序已启动。正在模拟生成日志...")

    try:
        for i in range(50):
            if i % 10 == 0:
                # 演示如何添加 "extra" 标签 (它们会被 LokiEmitter 提取为标签)
                logging.warning(
                    f"这是一条带 [extra tags] 的警告日志 (ID: {i})。",
                    extra={"tags": {"request_id": f"req-{i * 100}", "user": "demo_user"}}
                )
            else:
                logging.info(f"这是第 {i} 条模拟日志消息。")

            time.sleep(0.3)

        logging.info("日志模拟完成。等待最后的上传...")
        # 等待一段时间，确保上传线程有机会处理剩余日志
        time.sleep(2)

    except KeyboardInterrupt:
        logging.info("收到关闭信号 (KeyboardInterrupt)。")

    finally:
        logging.info("正在关闭应用程序...")

        # 优雅关闭：调用 Handler 的 stop 方法 (触发线程关闭和队列清空)
        loki_uploader_handler.stop()

        # 原有的手动清空队列逻辑现在由 loki_uploader_handler.stop() 处理

        print("应用程序已安全关闭。")
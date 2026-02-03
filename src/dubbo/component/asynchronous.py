import queue
import threading
import time
import uuid
from typing import Callable, Dict, Optional

from dubbo.loggers import loggerFactory

# 配置日志
_LOGGER = loggerFactory.get_logger()

# 存储方法配置
cls_method_config = {}


class AsyncLocalCallable:
    """
    基于本地队列的异步任务处理器
    抛弃 Redis 依赖，采用 Python 内置 Queue 实现
    """

    # 全局任务队列 (线程安全)
    _task_queue = queue.Queue()
    # 结果存储: { task_id: { "status": "...", "result": ... } }
    _results: Dict[str, dict] = {}
    _result_lock = threading.Lock()

    # 结果保留时长 (秒)
    RESULT_EXPIRE = 3600

    def __init__(self):
        self._stop_event = threading.Event()
        self._threads = []

    @staticmethod
    def register_method(method_name: str, method_instance: Callable, thread_num: int = 1):
        """
        注册方法，并指定处理该方法的后台线程数量
        """
        cls_method_config[method_name] = {
            "instance": method_instance,
            "thread_num": max(1, thread_num)
        }
        _LOGGER.info(f"本地异步方法注册成功: {method_name}, 线程数: {thread_num}")

    @classmethod
    def call_async(cls, method_name: str, args: tuple = (), kwargs: dict = None, callback_url: str = None) -> str:
        """
        发起异步调用，将任务放入本地队列
        """
        if method_name not in cls_method_config:
            raise ValueError(f"Method {method_name} not registered")

        task_id = str(uuid.uuid4())
        task_data = {
            "task_id": task_id,
            "method_name": method_name,
            "args": args,
            "kwargs": kwargs or {},
            "callback_url": callback_url,
            "timestamp": time.time()
        }

        # 初始化结果状态
        with cls._result_lock:
            cls._results[task_id] = {"status": "PENDING", "timestamp": time.time()}

        cls._task_queue.put(task_data)
        _LOGGER.info(f"异步任务已入队: {method_name}, task_id: {task_id}")
        return task_id

    def _worker_loop(self):
        """
        消费者线程主循环
        """
        while not self._stop_event.is_set():
            try:
                # 阻塞获取任务，超时设为 1秒以便响应停止事件
                task_data = self._task_queue.get(timeout=1)

                task_id = task_data["task_id"]
                method_name = task_data["method_name"]
                args = task_data["args"]
                kwargs = task_data["kwargs"]
                callback_url = task_data.get("callback_url")
                kwargs["task_id"] = task_id
                _LOGGER.info(f"开始执行任务: {method_name} (ID: {task_id})")

                # 执行具体方法
                try:
                    instance = cls_method_config[method_name]["instance"]
                    result = instance(*args, **kwargs)

                    result_data = {
                        "status": "SUCCESS",
                        "result": result,
                        "timestamp": time.time()
                    }
                except Exception as e:
                    _LOGGER.error(f"任务执行异常: {e}", exc_info=True)
                    result_data = {
                        "status": "FAILED",
                        "error": str(e),
                        "timestamp": time.time()
                    }

                # 存入本地结果字典
                with self._result_lock:
                    self._results[task_id] = result_data

                # 如果有回调则执行 (示例保留逻辑)
                if callback_url:
                    self._execute_callback(callback_url, task_id, result_data)

                # 标记任务完成
                self._task_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                _LOGGER.error(f"消费者线程异常: {e}")

    def _execute_callback(self, url: str, task_id: str, data: dict):
        """执行回调的简单占位"""
        import httpx
        try:
            # 实际生产中建议再套一层异步或线程池执行回调，防止阻塞消费者
            with httpx.Client() as client:
                client.post(url, json={"task_id": task_id, "data": data}, timeout=5.0)
        except Exception as e:
            _LOGGER.error(f"任务 {task_id} 回调失败: {e}")

    def start_consumer(self):
        """
        启动后台线程
        """
        # 计算总线程需求
        for method_name, config in cls_method_config.items():
            thread_num = config.get("thread_num", 1)
            for i in range(thread_num):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"LocalWorker-{method_name}-{i + 1}"
                )
                t.daemon = True
                t.start()
                self._threads.append(t)

        # 启动清理过期结果的守护线程
        cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        cleanup_thread.start()

        _LOGGER.info(f"共启动了 {len(self._threads)} 个本地消费者线程")

    def _cleanup_loop(self):
        """定期清理过期的任务结果，防止内存溢出"""
        while not self._stop_event.is_set():
            time.sleep(300)  # 每5分钟清理一次
            now = time.time()
            with self._result_lock:
                expired_keys = [
                    tid for tid, data in self._results.items()
                    if now - data.get("timestamp", 0) > self.RESULT_EXPIRE
                ]
                for tid in expired_keys:
                    del self._results[tid]
            if expired_keys:
                _LOGGER.info(f"清理了 {len(expired_keys)} 条过期任务记录")

    def stop_consumer(self):
        """安全停止"""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=1)
        self._threads.clear()

    @classmethod
    def get_result(cls, task_id: str) -> Optional[dict]:
        """从内存获取任务结果"""
        with cls._result_lock:
            return cls._results.get(task_id)


# 兼容性导出
AsyncRpcCallable = AsyncLocalCallable
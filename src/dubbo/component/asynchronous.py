import json
import threading
import uuid
from typing import Callable

from dubbo.constants import common_constants
from dubbo.loggers import loggerFactory
from dubbo.component.redis_client import RedisClient

# 配置日志
_LOGGER = loggerFactory.get_logger()

cls_method_config = {}

class AsyncRpcCallable:
    """
    异步 RPC 调用类
    支持按方法配置独立队列和并发线程数
    """
    # 存储格式: { method_name: {"instance": func, "thread_num": int} }
    QUEUE_PREFIX = f"rpc_queue_{common_constants.DEFAULT_SERVER_NAME}_{common_constants.ENV_KEY}"
    RESULT_EXPIRE = 3600
    try:
        redis = RedisClient()
        redis.r.ping()
    except Exception as e:
        _LOGGER.error(f"无法连接到 Redis: {e}")
        redis = None

    def __init__(self):
        self._stop_event = threading.Event()
        self._threads = []

    @staticmethod
    def register_method(method_name: str, method_instance: Callable, thread_num: int = 1):
        """
        注册方法，并指定处理该方法的后台线程数量
        :param method_name: 方法名
        :param method_instance: 回调函数
        :param thread_num: 该方法的并发消费者线程数
        """
        cls_method_config[method_name] = {
            "instance": method_instance,
            "thread_num": max(1, thread_num)
        }
        _LOGGER.info(f"方法 '{method_name}' 注册成功，配置线程数: {thread_num}")

    def pushlish_task(self, method_name: str, data: dict) -> str:
        """
        发布任务到该方法专属的队列中
        """
        if method_name not in cls_method_config:
            raise Exception(f"方法 '{method_name}' 未注册")

        task_id = str(uuid.uuid4())
        task_payload = {
            "task_id": task_id,
            "method_name": method_name,
            "data": data
        }

        # 每个方法对应一个独立的 List 队列
        queue_key = f"{self.QUEUE_PREFIX}_{method_name}"

        try:
            self.redis.r.lpush(queue_key, json.dumps(task_payload))
            _LOGGER.info(f"任务 {task_id} 已发布至队列 {queue_key}")
        except Exception as e:
            _LOGGER.error(f"发布任务失败: {e}")
            raise

        return task_id

    def _worker_loop(self, method_name: str):
        """
        特定方法的消费者线程逻辑
        """
        queue_key = f"{self.QUEUE_PREFIX}_{method_name}"
        handler = cls_method_config[method_name]["instance"]

        _LOGGER.info(f"线程 {threading.current_thread().name} 开始监听队列: {queue_key}")

        while not self._stop_event.is_set():
            try:
                # 阻塞读取专属队列
                raw_data = self.redis.r.brpop(queue_key, timeout=2)

                if raw_data:
                    _, payload_str = raw_data
                    payload = json.loads(payload_str)

                    task_id = payload.get("task_id")
                    params = payload.get("data")

                    # 执行业务逻辑
                    try:
                        result = handler(params)
                        status = "success"
                        _LOGGER.info(f"任务 {task_id} 执行成功")
                    except Exception as e:
                        result = str(e)
                        status = "error"
                        _LOGGER.error(f"任务 {task_id} 执行出错: {e}")

                    # 写入结果
                    result_key = f"{task_id}_result"
                    result_data = json.dumps({
                        "status": status,
                        "result": result,
                        "task_id": task_id
                    })
                    self.redis.set(result_key, result_data, ex=self.RESULT_EXPIRE)

            except Exception as e:
                if "Authentication required" in str(e):
                    _LOGGER.critical("Redis 认证失败，消费者线程退出")
                    break
                _LOGGER.error(f"消费者线程异常: {e}")

    def start_consumer(self):
        """
        为所有注册的方法启动指定数量的后台线程
        """
        for method_name, config in cls_method_config.items():
            _LOGGER.info(f"启动消费者线程: {method_name}")
            thread_num = config.get("thread_num", 1)
            for i in range(thread_num):
                t_name = f"Worker-{method_name}-{i + 1}"
                t = threading.Thread(
                    target=self._worker_loop,
                    args=(method_name,),
                    name=t_name
                )
                t.daemon = True
                t.start()
                self._threads.append(t)

        _LOGGER.info(f"共启动了 {len(self._threads)} 个消费者线程")

    def stop_consumer(self):
        """
        安全停止所有线程
        """
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=1)
        self._threads.clear()

    @staticmethod
    def get_result(task_id: str) -> dict:
        """
        获取任务结果
        """
        result_key = f"{task_id}_result"
        result = AsyncRpcCallable.redis.get(result_key)
        if result:
            return json.loads(result)
        return None

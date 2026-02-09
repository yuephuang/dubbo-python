import threading
import time

from prometheus_client import Counter, Histogram, Gauge, REGISTRY, pushadd_to_gateway

from dubbo.constants import common_constants
labelnames = ["server_name", 'method_name', 'endpoint', 'status']


class MetricsCollector:
    _instances = {}  # 用于缓存每个server_name的实例
    _lock = threading.Lock()

    def __new__(cls, server_name, label_names=None):
        """单例模式，确保每个server_name只有一个实例"""
        with cls._lock:
            if server_name not in cls._instances:
                instance = super().__new__(cls)
                instance.__init__(server_name, label_names)
                cls._instances[server_name] = instance
            return cls._instances[server_name]

    def __init__(self, server_name, label_names=None):
        # 防止重复初始化
        if hasattr(self, '_initialized'):
            return

        self.server_name = server_name
        self.label_names = label_names or labelnames

        # 预创建并注册所有指标
        self._init_metrics()
        self._start_push_thread()
        self._initialized = True

    def _init_metrics(self):
        """初始化所有指标"""
        # 使用唯一的前缀避免冲突
        prefix = f"{self.server_name}_"

        # 请求计数器
        self._request_counter = Counter(
            name=f"request_count",
            documentation="request count",
            labelnames=self.label_names,
            registry=REGISTRY
        )

        # 请求耗时直方图
        self._request_duration = Histogram(
            name=f"request_duration_seconds",
            documentation="request duration in seconds",
            labelnames=["server_name", 'method_name', 'endpoint'],
            registry=REGISTRY
        )

        # 正在处理的请求数
        self._request_in_progress = Gauge(
            name=f"request_in_progress",
            documentation="request in progress",
            labelnames=["server_name", 'method_name', 'endpoint'],
            registry=REGISTRY
        )

        # 缓存使用计数器
        self._use_cache_count = Counter(
            name=f"use_cache_count",
            documentation="use cache count",
            labelnames=self.label_names,
            registry=REGISTRY
        )

    @property
    def request_count(self) -> Counter:
        """获取请求计数器"""
        return self._request_counter

    @property
    def request_duration(self) -> Histogram:
        """获取请求耗时直方图"""
        return self._request_duration

    @property
    def request_in_progress(self) -> Gauge:
        """获取正在处理的请求数仪表"""
        return self._request_in_progress

    @property
    def use_cache_count(self) -> Counter:
        """获取缓存使用计数器"""
        return self._use_cache_count

    def _start_push_thread(self):
        """启动后台线程，每隔15秒上报一次"""

        def run_forever():
            while True:
                self.pushgateway()
                time.sleep(15)  # 每隔15秒

        # 设置为守护线程，这样主程序退出时，该线程也会自动退出
        t = threading.Thread(target=run_forever, daemon=True, name=f"PushThread_{self.server_name}")
        t.start()

    def pushgateway(self):
        if common_constants.PUSHGATEWAY_URL:
            try:
                pushadd_to_gateway(
                    gateway=common_constants.PUSHGATEWAY_URL,
                    job=f"{common_constants.ENV_KEY}_{common_constants.HOST_NAME}_{self.server_name}",
                    registry=REGISTRY
                )
            except Exception as e:
                # 实际应用中建议使用 logger
                print(f"[{self.server_name}] 上报 Pushgateway 失败: {e}")
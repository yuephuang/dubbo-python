import logging
import time
from contextlib import contextmanager

# 假设这些是你的依赖，根据实际情况调整
from prometheus_client import (
    Counter, Histogram, Gauge, Info, generate_latest,
    REGISTRY
)

from dubbo.protocol.triple.constants import GRpcCode

_LOGGER = logging.getLogger(__name__)

# ==================== 全局指标定义 ====================
# 请求持续时间直方图（按方法名和状态标签）
REQUEST_DURATION = Histogram(
    'method_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'grpc_status_code'],  # grpc_status_code: success, error, rate_limited, auth_failed等
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

# 请求总数计数器
REQUEST_TOTAL = Counter(
    'method_requests_total',
    'Total number of requests',
    ['method', 'grpc_status_code', 'error_type']  # error_type: validation, auth, rate_limit, business, system
)

# 当前正在处理的请求数
REQUESTS_IN_PROGRESS = Gauge(
    'method_requests_in_progress',
    'Current number of requests being processed',
    ['method']
)

# 缓存命中/未命中
CACHE_OPERATIONS = Counter(
    'method_cache_operations_total',
    'Cache operations count',
    ['method', 'operation']  # operation: hit, miss, set, delete
)

# 异步任务相关指标
ASYNC_TASKS = Counter(
    'method_async_tasks_total',
    'Async tasks count',
    ['method', 'action']  # action: published, completed, failed
)

# 业务响应大小分布
RESPONSE_SIZE = Histogram(
    'method_response_size_bytes',
    'Response size in bytes',
    ['method'],
    buckets=(1024, 5120, 10240, 51200, 102400, 512000, 1048576)
)

# 服务信息
SERVICE_INFO = Info('service_info', 'Service information')


# ==================== 上下文管理器用于跟踪请求 ====================
@contextmanager
def track_request(method_name: str):
    """跟踪请求的上下文管理器"""
    REQUESTS_IN_PROGRESS.labels(method=method_name).inc()
    start_time = time.time()
    grpc_status_code: int = GRpcCode.UNKNOWN.value

    try:
        yield
        grpc_status_code: int = GRpcCode.OK.value
    except Exception:
        grpc_status_code = GRpcCode.RESOURCE_EXHAUSTED.value
        raise
    finally:
        REQUESTS_IN_PROGRESS.labels(method=method_name).dec()
        duration = time.time() - start_time
        REQUEST_DURATION.labels(method=method_name, grpc_status_code=grpc_status_code).observe(duration)


# ==================== 增强的 MetricsCollector 类 ====================
class EnhancedMetricsCollector:
    """增强的指标收集器"""

    def __init__(self, service_name: str, service_version: str):
        self.service_name = service_name
        self.service_version = service_version

        # 设置服务信息
        SERVICE_INFO.info({
            'service_name': service_name,
            'version': service_version,
            'language': 'python'
        })

    def record_request(self, method_name: str, grpc_status_code: int = GRpcCode.OK.value, duration: float = None):
        """记录请求指标"""
        REQUEST_TOTAL.labels(
            method=method_name,
            grpc_status_code=grpc_status_code,
        ).inc()

        if duration is not None:
            REQUEST_DURATION.labels(method=method_name, grpc_status_code=grpc_status_code).observe(duration)

    def record_cache_operation(self, method_name: str, operation: str):
        """记录缓存操作"""
        CACHE_OPERATIONS.labels(method=method_name, operation=operation).inc()

    def record_async_task(self, method_name: str, action: str):
        """记录异步任务"""
        ASYNC_TASKS.labels(method=method_name, action=action).inc()

    def record_response_size(self, method_name: str, size_bytes: int):
        """记录响应大小"""
        RESPONSE_SIZE.labels(method=method_name).observe(size_bytes)

    def start_request_timer(self, method_name: str):
        """开始请求计时器"""
        return RequestTimer(method_name)

    def get_metrics(self):
        """获取所有指标"""
        return generate_latest(REGISTRY)


# ==================== 请求计时器类 ====================
class RequestTimer:
    """请求计时器，自动记录持续时间"""

    def __init__(self, method_name: str):
        self.method_name = method_name
        self.start_time = time.time()
        self.grpc_status_code: int = GRpcCode.UNKNOWN.value
        self.error_type = "none"

    def set_grpc_status_code(self, grpc_status_code: int, error_type: str = None):
        """设置请求状态"""
        self.grpc_status_code = grpc_status_code
        if error_type:
            self.error_type = error_type

    def __enter__(self):
        REQUESTS_IN_PROGRESS.labels(method=self.method_name).inc()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        REQUESTS_IN_PROGRESS.labels(method=self.method_name).dec()

        # 记录指标
        REQUEST_TOTAL.labels(
            method=self.method_name,
            grpc_status_code=self.grpc_status_code,
        ).inc()

        REQUEST_DURATION.labels(
            method=self.method_name,
            grpc_status_code=self.grpc_status_code
        ).observe(duration)

        # 返回 False 让异常继续传播
        return False
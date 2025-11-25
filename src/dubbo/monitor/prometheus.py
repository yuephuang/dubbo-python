import threading
import time
from dataclasses import dataclass
from enum import Enum
from time import sleep
from typing import List, Dict, Any

import psutil


class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass
class MetricLabel:
    endpoint: str = ""
    method: str = ""
    status: str = ""
    le: str = ""  # 用于直方图的 bucket label
    device: str = ""
    type: str = ""


@dataclass
class MetricSample:
    value: float
    labels: MetricLabel
    # 【修复 1: 为直方图样本添加后缀标识】
    name_suffix: str = ""


@dataclass
class Metric:
    name: str
    help_text: str
    metric_type: MetricType
    samples: List[MetricSample]


class SystemMetricsCollector:
    """系统指标收集器，运行在独立的后台线程中，定期收集系统资源信息。"""

    def __init__(self, update_interval: int = 5):
        self.update_interval = update_interval
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # 系统指标数据
        self.cpu_usage = 0.0
        self.memory_usage = 0.0
        self.memory_total = 0.0
        self.memory_available = 0.0
        self.disk_usage = 0.0
        self.disk_total = 0.0
        self.network_bytes_sent = 0
        self.network_bytes_recv = 0
        self.gpu_metrics = {}

        self._initialize_gpu_metrics()

    def _initialize_gpu_metrics(self):
        """初始化GPU指标 - 简化版本，不依赖GPUtil"""
        # 尝试使用nvidia-smi命令获取GPU信息，如果不可用则创建空指标
        self.gpu_metrics["gpu_0"] = {
            'usage': 0.0,
            'memory_used': 0.0,
            'memory_total': 0.0,
            'temperature': 0.0
        }

    def _collect_gpu_metrics_simple(self):
        """简化版GPU指标收集 (尝试使用 nvidia-smi)"""
        try:
            # 尝试使用nvidia-smi命令获取GPU信息
            import subprocess
            # 查询 GPU 利用率, 内存使用量(MiB), 内存总量(MiB), 温度(C)
            result = subprocess.run([
                'nvidia-smi',
                '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                # 假设输出为逗号分隔的四个浮点数
                gpu_data = [float(val.strip()) for val in result.stdout.strip().split(',')]
                if len(gpu_data) >= 4:
                    self.gpu_metrics["gpu_0"] = {
                        'usage': gpu_data[0],  # %
                        'memory_used': gpu_data[1],  # MiB
                        'memory_total': gpu_data[2],  # MiB
                        'temperature': gpu_data[3]  # C
                    }
        except Exception:
            # 如果 nvidia-smi 不可用或失败，保持默认值
            pass

    def _collect_system_metrics(self):
        """收集系统指标"""
        # CPU使用率
        self.cpu_usage = psutil.cpu_percent(interval=1)

        # 内存使用情况
        memory = psutil.virtual_memory()
        self.memory_usage = memory.percent
        self.memory_total = memory.total / (1024 ** 3)  # 转换为GB
        self.memory_available = memory.available / (1024 ** 3)  # 转换为GB

        # 磁盘使用情况
        disk = psutil.disk_usage('/')
        self.disk_usage = disk.percent
        self.disk_total = disk.total / (1024 ** 3)  # 转换为GB

        # 网络IO
        net_io = psutil.net_io_counters()
        self.network_bytes_sent = net_io.bytes_sent
        self.network_bytes_recv = net_io.bytes_recv

        # GPU使用情况（简化版本）
        self._collect_gpu_metrics_simple()

    def start(self):
        """启动指标收集线程"""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run)
            self._thread.daemon = True
            self._thread.start()

    def stop(self):
        """停止指标收集线程"""
        self._running = False
        if self._thread:
            self._thread.join()

    def _run(self):
        """后台运行收集指标"""
        while self._running:
            with self._lock:
                self._collect_system_metrics()
            sleep(self.update_interval)

    def get_system_metrics(self) -> Dict[str, Any]:
        """获取当前系统指标 (线程安全)"""
        with self._lock:
            return {
                'cpu_usage': self.cpu_usage,
                'memory_usage': self.memory_usage,
                'memory_total': self.memory_total,
                'memory_available': self.memory_available,
                'disk_usage': self.disk_usage,
                'disk_total': self.disk_total,
                'network_bytes_sent': self.network_bytes_sent,
                'network_bytes_recv': self.network_bytes_recv,
                'gpu_metrics': self.gpu_metrics.copy()
            }


class PrometheusMetrics:
    """业务指标注册和更新类，负责生成 Prometheus 格式输出"""

    def __init__(self, method_name: str, system_collector: SystemMetricsCollector):
        self.method_name = method_name
        self.system_collector = system_collector
        # 【修复 2: 添加线程锁以确保业务指标更新的线程安全】
        self._lock = threading.Lock()
        self.metrics = self._initialize_metrics()
        self.start_time = time.time()

    def _initialize_metrics(self) -> Dict[str, Metric]:
        base_labels = MetricLabel(endpoint=f"/{self.method_name}", method="POST")

        metrics_dict = {
            "requests_total": Metric(
                name=f"{self.method_name}_requests_total",
                help_text=f"Total number of {self.method_name} requests",
                metric_type=MetricType.COUNTER,
                samples=[
                    MetricSample(value=14123.0, labels=MetricLabel(**{**base_labels.__dict__, "status": "200"})),
                    MetricSample(value=24.0, labels=MetricLabel(**{**base_labels.__dict__, "status": "400"}))
                ]
            ),
            "requests_created": Metric(
                name=f"{self.method_name}_requests_created",
                help_text=f"Total number of {self.method_name} requests",
                metric_type=MetricType.GAUGE,
                samples=[
                    # 仅作为示例，实际应使用启动时间或首次请求时间
                    MetricSample(value=time.time(),
                                 labels=MetricLabel(**{**base_labels.__dict__, "status": "200"})),
                    MetricSample(value=time.time(),
                                 labels=MetricLabel(**{**base_labels.__dict__, "status": "400"}))
                ]
            ),
            "request_duration_seconds": Metric(
                name=f"{self.method_name}_request_duration_seconds",
                help_text=f"Time spent processing {self.method_name} request",
                metric_type=MetricType.HISTOGRAM,
                samples=self._create_histogram_samples(base_labels)
            ),
            "requests_in_progress": Metric(
                name=f"{self.method_name}_requests_in_progress",
                help_text=f"Number of {self.method_name} requests in progress",
                metric_type=MetricType.GAUGE,
                samples=[MetricSample(value=0.0, labels=base_labels)]
            )
        }

        # 添加系统指标
        metrics_dict.update(self._create_system_metrics())
        return metrics_dict

    def _create_system_metrics(self) -> Dict[str, Metric]:
        """创建系统指标"""
        system_metrics = {}

        # CPU指标
        system_metrics["cpu_usage"] = Metric(
            name="system_cpu_usage_percent",
            help_text="System CPU usage percentage",
            metric_type=MetricType.GAUGE,
            samples=[MetricSample(value=0.0, labels=MetricLabel(type="user"))]
        )

        # 内存指标
        system_metrics["memory_usage"] = Metric(
            name="system_memory_usage_percent",
            help_text="System memory usage percentage",
            metric_type=MetricType.GAUGE,
            samples=[MetricSample(value=0.0, labels=MetricLabel(type="used"))]
        )

        system_metrics["memory_bytes"] = Metric(
            name="system_memory_bytes",
            help_text="System memory usage in bytes",
            metric_type=MetricType.GAUGE,
            samples=[
                MetricSample(value=0.0, labels=MetricLabel(type="total")),
                MetricSample(value=0.0, labels=MetricLabel(type="available")),
                MetricSample(value=0.0, labels=MetricLabel(type="used"))
            ]
        )

        # 磁盘指标
        system_metrics["disk_usage"] = Metric(
            name="system_disk_usage_percent",
            help_text="System disk usage percentage",
            metric_type=MetricType.GAUGE,
            samples=[MetricSample(value=0.0, labels=MetricLabel(type="used"))]
        )

        system_metrics["disk_bytes"] = Metric(
            name="system_disk_bytes",
            help_text="System disk usage in bytes",
            metric_type=MetricType.GAUGE,
            samples=[
                MetricSample(value=0.0, labels=MetricLabel(type="total")),
                MetricSample(value=0.0, labels=MetricLabel(type="used"))
            ]
        )

        # 网络指标
        system_metrics["network_bytes"] = Metric(
            name="system_network_bytes_total",
            help_text="System network bytes",
            metric_type=MetricType.COUNTER,
            samples=[
                MetricSample(value=0.0, labels=MetricLabel(type="sent")),
                MetricSample(value=0.0, labels=MetricLabel(type="received"))
            ]
        )

        # GPU指标
        system_metrics["gpu_usage"] = Metric(
            name="system_gpu_usage_percent",
            help_text="GPU usage percentage",
            metric_type=MetricType.GAUGE,
            samples=[]
        )

        system_metrics["gpu_memory"] = Metric(
            name="system_gpu_memory_bytes",
            help_text="GPU memory usage in bytes",
            metric_type=MetricType.GAUGE,
            samples=[]
        )

        system_metrics["gpu_temperature"] = Metric(
            name="system_gpu_temperature_celsius",
            help_text="GPU temperature in Celsius",
            metric_type=MetricType.GAUGE,
            samples=[]
        )

        return system_metrics

    def _create_histogram_samples(self, base_labels: MetricLabel) -> List[MetricSample]:
        """创建直方图的 bucket, sum 和 count 样本"""
        buckets = [
            ('0.005', 0.0), ('0.01', 0.0), ('0.025', 0.0), ('0.05', 0.0),
            ('0.075', 0.0), ('0.1', 0.0), ('0.25', 0.0), ('0.5', 0.0),
            ('0.75', 0.0), ('1.0', 0.0), ('2.5', 0.0), ('5.0', 0.0),
            ('7.5', 0.0), ('10.0', 0.0), ('+Inf', 0.0)
        ]

        samples = []
        for le, value in buckets:
            # 【修复 3: bucket 样本，使用 _bucket 后缀标识】
            samples.append(MetricSample(
                value=value,
                labels=MetricLabel(**{**base_labels.__dict__, "le": le}),
                name_suffix="_bucket"
            ))

        # sum 样本
        samples.append(MetricSample(
            value=0.0,
            labels=base_labels,
            name_suffix="_sum"
        ))

        # count 样本
        samples.append(MetricSample(
            value=0,
            labels=base_labels,
            name_suffix="_count"
        ))

        return samples

    def _format_labels(self, labels: MetricLabel) -> str:
        """格式化标签字典为 Prometheus 字符串"""
        label_parts = []
        for key, value in labels.__dict__.items():
            if value is not None and value != "":
                # 确保标签值是 Prometheus 兼容的字符串格式
                label_parts.append(f'{key}="{value}"')
        return "{" + ",".join(label_parts) + "}" if label_parts else ""

    def _update_system_metrics(self):
        """更新系统指标数据"""
        system_data = self.system_collector.get_system_metrics()

        # 更新CPU使用率
        self.metrics["cpu_usage"].samples[0].value = system_data['cpu_usage']

        # 更新内存指标
        self.metrics["memory_usage"].samples[0].value = system_data['memory_usage']

        # 转换回字节 (GB * (1024**3))
        gb_to_bytes = (1024 ** 3)

        self.metrics["memory_bytes"].samples[0].value = system_data['memory_total'] * gb_to_bytes  # Total
        self.metrics["memory_bytes"].samples[1].value = system_data['memory_available'] * gb_to_bytes  # Available
        # Used = Total - Available
        self.metrics["memory_bytes"].samples[2].value = (system_data['memory_total'] - system_data[
            'memory_available']) * gb_to_bytes

        # 更新磁盘指标
        self.metrics["disk_usage"].samples[0].value = system_data['disk_usage']
        self.metrics["disk_bytes"].samples[0].value = system_data['disk_total'] * gb_to_bytes  # Total
        # Used = Total * Usage%
        self.metrics["disk_bytes"].samples[1].value = (system_data['disk_total'] * system_data[
            'disk_usage'] / 100) * gb_to_bytes

        # 更新网络指标
        self.metrics["network_bytes"].samples[0].value = system_data['network_bytes_sent']
        self.metrics["network_bytes"].samples[1].value = system_data['network_bytes_recv']

        # 更新GPU指标
        self._update_gpu_metrics(system_data['gpu_metrics'])

    def _update_gpu_metrics(self, gpu_data: Dict):
        """更新GPU指标"""
        gpu_usage_samples = []
        gpu_memory_samples = []
        gpu_temp_samples = []

        # MiB to Bytes conversion
        mib_to_bytes = 1024 * 1024

        for device_id, metrics in gpu_data.items():
            device_label = MetricLabel(device=device_id)

            # GPU使用率
            gpu_usage_samples.append(
                MetricSample(value=metrics['usage'], labels=device_label)
            )

            # GPU内存 (MiB 转换为 Bytes)
            gpu_memory_samples.extend([
                MetricSample(value=metrics['memory_used'] * mib_to_bytes,
                             labels=MetricLabel(**{**device_label.__dict__, "type": "used"})),
                MetricSample(value=metrics['memory_total'] * mib_to_bytes,
                             labels=MetricLabel(**{**device_label.__dict__, "type": "total"}))
            ])

            # GPU温度
            gpu_temp_samples.append(
                MetricSample(value=metrics['temperature'], labels=device_label)
            )

        self.metrics["gpu_usage"].samples = gpu_usage_samples
        self.metrics["gpu_memory"].samples = gpu_memory_samples
        self.metrics["gpu_temperature"].samples = gpu_temp_samples

    def generate_metrics_output(self) -> str:
        """生成完整的Prometheus指标输出 (线程安全)"""
        with self._lock:  # 【修复 2: 锁定指标字典，防止在读取/格式化时被修改】
            self._update_system_metrics()  # 先更新系统指标数据

            output_lines = []

            for metric in self.metrics.values():
                # 跳过没有样本的指标
                if not metric.samples:
                    continue

                # 添加help和type行
                output_lines.append(f"# HELP {metric.name} {metric.help_text}")
                output_lines.append(f"# TYPE {metric.name} {metric.metric_type.value}")

                # 添加指标样本
                for sample in metric.samples:
                    labels_str = self._format_labels(sample.labels)

                    # 【修复 4: 处理直方图的后缀，确保 Prometheus 格式正确】
                    if metric.metric_type == MetricType.HISTOGRAM and sample.name_suffix:
                        # 直方图样本的名称需要加上后缀
                        metric_name_full = f"{metric.name}{sample.name_suffix}{labels_str}"
                    else:
                        # Counter/Gauge 指标，或没有特殊后缀的直方图样本（不推荐，但作为通用处理）
                        metric_name_full = f"{metric.name}{labels_str}"

                    output_lines.append(f"{metric_name_full} {sample.value}")

                output_lines.append("")  # 指标之间的空行

            return "\n".join(output_lines)

    def increment_request_total(self, status: str = "200"):
        """增加请求总数 (线程安全)"""
        with self._lock:  # 【修复 2: 锁定以防止并发修改】
            metric = self.metrics["requests_total"]
            for sample in metric.samples:
                if sample.labels.status == status:
                    sample.value += 1
                    break

    def set_requests_in_progress(self, count: float):
        """设置进行中的请求数 (线程安全)"""
        with self._lock:  # 【修复 2: 锁定以防止并发修改】
            self.metrics["requests_in_progress"].samples[0].value = count

    def observe_request_duration(self, duration: float):
        """观察请求耗时，更新直方图 (线程安全)"""
        with self._lock:  # 【修复 2: 锁定以防止并发修改】
            histogram = self.metrics["request_duration_seconds"]

            # 遍历所有样本，根据 name_suffix 更新 count/sum/buckets
            for sample in histogram.samples:
                if sample.name_suffix == "_bucket":
                    # 仅处理桶样本
                    le_label = sample.labels.le

                    if le_label:
                        if le_label == "+Inf":
                            # +Inf 桶总是递增
                            sample.value += 1
                        else:
                            # 其他桶，检查是否小于等于 le 值
                            try:
                                le_value = float(le_label)
                                if duration <= le_value:
                                    sample.value += 1
                            except ValueError:
                                # 忽略格式错误
                                pass
                elif sample.name_suffix == "_count":
                    sample.value += 1  # count 递增
                elif sample.name_suffix == "_sum":
                    sample.value += duration  # sum 累加


class MetricsCollector:
    """指标收集器管理器，负责启动系统收集线程和管理业务指标实例"""

    def __init__(self, system_update_interval: int = 5):
        self.system_collector = SystemMetricsCollector(update_interval=system_update_interval)
        self.system_collector.start()  # 启动系统指标收集
        self.metrics_registry = {}

    def register_metrics(self, method_name: str) -> PrometheusMetrics:
        if method_name not in self.metrics_registry:
            self.metrics_registry[method_name] = PrometheusMetrics(method_name, self.system_collector)
        return self.metrics_registry[method_name]

    def get_method_metrics(self, method_name: str) -> PrometheusMetrics:
        # get_method_metrics 和 register_metrics 逻辑一致，可以简化
        return self.register_metrics(method_name)

    def get_all_metrics(self) -> str:
        """获取所有已注册的指标的 Prometheus 格式输出"""
        all_output = []
        for metrics in self.metrics_registry.values():
            # 这里调用 generate_metrics_output 会在内部锁定 PrometheusMetrics
            all_output.append(metrics.generate_metrics_output())
        metrics_data = "\n".join(all_output)
        return metrics_data

    def stop(self):
        """停止指标收集"""
        self.system_collector.stop()


# 使用示例
if __name__ == "__main__":
    # 安装依赖: pip install psutil

    collector = MetricsCollector(system_update_interval=2)

    try:
        # 注册业务指标
        user_metrics = collector.register_metrics("user_login")
        order_metrics = collector.register_metrics("create_order")

        # 模拟业务操作
        user_metrics.increment_request_total("200")
        user_metrics.increment_request_total("200")
        user_metrics.set_requests_in_progress(3)
        user_metrics.observe_request_duration(0.12)
        user_metrics.observe_request_duration(0.003)
        user_metrics.observe_request_duration(1.5)

        order_metrics.increment_request_total("400")
        order_metrics.observe_request_duration(0.05)

        # 等待系统指标收集
        print("等待系统指标收集...")
        time.sleep(3)

        # 生成完整的监控指标输出
        print("\n--- Prometheus Metrics Output ---")
        print(collector.get_all_metrics())
        print("-------------------------------")

    finally:
        print("停止收集器...")
        collector.stop()
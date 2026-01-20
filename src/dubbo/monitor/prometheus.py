from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST


labelnames = ["server_name", 'method_name', 'endpoint', 'status']


class MetricsCollector:
    def __init__(self, server_name, label_names=None):
        self.server_name = server_name
        self.label_names = label_names or labelnames

    @property
    def request_count(self) -> Counter:
        return Counter(name=f"request_count",
                       documentation="request count",
                       labelnames=["server_name", 'method_name', 'endpoint', 'status']
                       )

    @property
    def request_duration(self) -> Histogram:
        return Histogram(name=f"request_duration",
                         documentation="request duration",
                         labelnames=["server_name", 'method_name', 'endpoint', 'status']
                         )

    @property
    def request_in_progess(self) -> Gauge:
        return Gauge(name=f"request_in_progess",
                     documentation="request in_progess",
                     labelnames=["server_name", 'method_name', 'endpoint', 'status']
                     )
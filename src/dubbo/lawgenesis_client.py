import asyncio
import datetime
import os
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Any

from v2.nacos import Instance

from dubbo.client import Client as DubboClient
from dubbo.component.nacos_client import NacosClinet
from dubbo.configcenter.lawgenes_config import LawClientConfig, NotifyConfig
from dubbo.configs import ReferenceConfig
from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.lawgenesis_proto.proto import lawgenesis_pb2
from dubbo.lawgenesis_proto import LawMetaData
from dubbo.lawgenesis_server import trace_context_manager
from dubbo.loggers import loggerFactory, CONTEXT_ID, TRACE_ID
from dubbo.notify import NoticeFactory, ServerMetaData

# 配置常量
CONNECTIONS_PER_IP = 3  # 每个 IP 建立的长连接数量（分摊 HTTP/2 Stream 压力）

_LOGGER = loggerFactory.get_logger()


class _IPConnectionPool:
    """
    管理单个 IP 实例的资源：
    1. 独立的线程池 (隔离故障，控制并发)
    2. 多个 DubboClient 连接 (避免 HTTP/2 单连接 100 Stream 限制)
    """

    def __init__(self, url_key: str, server_name: str, threads_per_ip: int = 10):
        self.url_key = url_key
        self.server_name = server_name
        self.weight = 10  # 初始权重

        # 1. 独立线程池
        self.executor = ThreadPoolExecutor(
            max_workers=threads_per_ip,
            thread_name_prefix=f"Dubbo-{server_name}-{url_key[-10:]}"
        )

        # 2. 建立多个连接
        self.clients: List[DubboClient] = []
        try:
            for _ in range(CONNECTIONS_PER_IP):
                client = DubboClient(reference=ReferenceConfig.from_url(url=url_key))
                self.clients.append(client)
        except Exception as e:
            _LOGGER.error(f"初始化连接池失败 {url_key}: {e}")
            # 如果初始化失败，确保清理已创建的资源
            self.shutdown()
            raise e

    def get_client(self) -> DubboClient:
        """从池中随机获取一个连接"""
        if not self.clients:
            raise RuntimeError(f"Connection pool for {self.url_key} is empty")
        return random.choice(self.clients)

    def adjust_weight(self, success: bool):
        """动态调整权重"""
        if success:
            self.weight = min(10, self.weight + 1)
        else:
            self.weight = max(1, self.weight - 1)

    def shutdown(self):
        """清理资源"""
        self.executor.shutdown(wait=False)
        # 这里假设 DubboClient 有 close 方法，如果有的话应该调用
        # for client in self.clients:
        #     client.close()
        self.clients.clear()


class _InvokeClient:
    def __init__(self, server_name: str, client_config: LawClientConfig, notify_config=None,
                 ):
        self.client_config = client_config or LawClientConfig()
        self.server_name = server_name
        self._pools: Dict[str, _IPConnectionPool] = {}

        self.nacos_client = NacosClinet()
        self._initialized = False
        self.notify_config = notify_config or NotifyConfig()
        self._notify_factory: Optional[NoticeFactory] = extensionLoader.get_extension(NoticeFactory, "feishu")()
        self._notify_factory.server_name = server_name
        self._notify_factory.url = self.notify_config.url

        self.request_deserializer = lawgenesis_pb2.LawgenesisRequest
        self.response_deserialize =  lawgenesis_pb2.LawgenesisReply
        self.retry_times = 2

    @staticmethod
    def get_authorization() -> lawgenesis_pb2.Auth:
        return lawgenesis_pb2.Auth(
            AUTY="lawgenesis",
            ACID="lawgenesis",
            ACKY="lawgenesis"
        )

    def server_key(self, ip, port):
        return f"tri://{ip}:{port}/{self.server_name}"

    def get_service(self, instances: List[Instance] = None):
        """
        更新服务列表。
        对比新旧实例列表，创建新 Pool，销毁旧 Pool。
        """
        instances = instances or self.nacos_client.get_service(server_name=self.server_name)
        current_keys = set()

        # 1. 更新或创建 Pool
        for instance in instances:
            key = self.server_key(instance.ip, instance.port)
            current_keys.add(key)

            if key not in self._pools:
                _LOGGER.info(f"Add new connection pool: {key}")
                try:
                    self._pools[key] = _IPConnectionPool(key, self.server_name,
                                                         common_constants.THREADS_PER_IP_MAP.get(self.server_name, 10))
                except Exception as e:
                    _LOGGER.error(f"Failed to create pool for {key}: {e}")

        # 2. 清理下线的 Pool
        existing_keys = list(self._pools.keys())
        for key in existing_keys:
            if key not in current_keys:
                _LOGGER.warning(f"Remove offline connection pool: {key}")
                pool = self._pools.pop(key)
                pool.shutdown()

    def subscribe(self):
        def cb(instance_list: List[Instance]):
            _LOGGER.info(f"subscribe instance_list: {instance_list}")
            self.get_service(instance_list)

        self.nacos_client.subscribe_service(server_name=self.server_name, group_name=common_constants.GROUP_KEY,
                                            listener=cb)

    def _get_server_metadata(self, message="") -> ServerMetaData:
        host_name = os.environ.get("HOSTNAME", "NOT HOSTNAME")
        return ServerMetaData(
            server_name=self.server_name,
            host="",
            host_name=host_name,
            intranet_ip="NOT INTRANET IP",
            internet_ip="NOT INTRANET IP",
            message=f"{message}",
            start_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def select_pool(self) -> _IPConnectionPool:
        """根据权重选择一个 IP 连接池"""
        if not self._pools:
            _LOGGER.warning(f"服务 {self.server_name} 实例列表为空，可能正在初始化...")
            # 重新建立连接
            self.get_service()
            time.sleep(self.retry_times)
            self.retry_times = min(self.retry_times * 2, 60)
            if not  self._pools:
                raise RuntimeError(f"No available instances found for server: {self.server_name}")

        # 提取 Pool 和权重
        pools = list(self._pools.values())
        weights = [p.weight for p in pools]

        # 随机加权选择
        selected_pool = random.choices(pools, weights=weights, k=1)[0]
        return selected_pool

    async def async_invoke(self, method_name: str, request_data: Any,
                           metadata: LawMetaData, timeout_second = 60.0,
                           request_serializer = None , response_deserializer =  None
                           ) -> lawgenesis_pb2.LawgenesisReply:
        loop = asyncio.get_running_loop()

        try:
            pool = self.select_pool()
            request_serializer = request_serializer or self.request_deserializer
            response_deserializer = response_deserializer or self.request_deserializer
            # 使用 asyncio.wait_for 包装协程
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    pool.executor,
                    self.invoke,
                    pool,
                    method_name,
                    request_data,
                    metadata,
                    request_serializer,
                    response_deserializer
                ),
                timeout=timeout_second
            )
            return result
        except asyncio.TimeoutError:
            # 处理超时逻辑
            error_msg = f"服务调用超时 ({timeout_second}s)"
            await self._notify_factory.async_send_table(
                title="🟡服务调用超时",
                subtitle=common_constants.DEFAULT_SERVER_NAME,
                elements=[self._get_server_metadata(message=error_msg)]
            )
            raise TimeoutError(error_msg)
        except Exception as e:
            await self._notify_factory.async_send_table(
                title="🔴服务调用失败",
                subtitle=common_constants.DEFAULT_SERVER_NAME,
                elements=[self._get_server_metadata(message=str(e))]
            )
            raise e

    def invoke(self, pool: _IPConnectionPool, method_name: str, request_data: Any, metadata: LawMetaData,
               request_serializer, response_deserializer):
        """
        实际执行调用的方法，运行在 pool.executor 线程中
        """
        metadata = metadata
        metadata.auth = self.get_authorization()

        law_request = request_serializer(
            DATA=request_data,
            BADA=metadata.basedata
        )

        # 尝试逻辑：在同一个 IP 池内尝试
        # 如果第一次失败，可能换一个 connection 再试一次
        last_error = None
        for _ in range(2):
            try:
                # 从池中获取一个 DubboClient (轮询或随机)
                client = pool.get_client()

                result = client.unary(
                    method_name=method_name,
                    request_serializer=request_serializer.SerializeToString,
                    response_deserializer=response_deserializer.FromString,
                )(law_request)

                # 成功，增加权重
                pool.adjust_weight(success=True)
                return result
            except Exception as e:
                _LOGGER.error(f"unary {method_name} failed on {pool.url_key}: {e}")
                last_error = e
                # 失败，降低权重
                pool.adjust_weight(success=False)

                # 如果权重太低，考虑是否要从池子里移除（根据你的业务逻辑）
                # 这里暂时只降权，由 get_service 负责移除完全不可用的

        # 如果重试后依然失败
        if pool.weight <= 1:
            self._pools.pop(pool.url_key, None)

        raise Exception(
            f"{method_name} invoke failed on {pool.url_key}, final weight: {pool.weight}. Error: {last_error}")


class LawgenesisClient:
    def __init__(self, server_url=None):
        self.__invoke_client: Dict[str, _InvokeClient] = {}
        self.server_url = server_url
        self._loop = None
        self._loop_thread = None

    def select_invoke_client(self, server_name: str, client_config: LawClientConfig = None,
                             ) -> _InvokeClient:
        if server_name not in self.__invoke_client:
            invoker = _InvokeClient(server_name, client_config, None)
            invoker.get_service()
            invoker.subscribe()
            self.__invoke_client[server_name] = invoker
        return self.__invoke_client[server_name]

    async def async_invoke(self, server_name, method_name, request_data,
                           client_config: LawClientConfig = None,
                           request_deserializer=None,
                           response_deserializer=None,
                           metadata=None,
                           timeout_second=60
                           ):
        invoke_client = self.select_invoke_client(server_name, client_config)
        metadata = metadata or LawMetaData(basedata=lawgenesis_pb2.BaseData())

        # 简单的 Trace ID 处理
        trace_id = TRACE_ID.get() if TRACE_ID.get() != "N/A" else uuid.uuid4().hex
        context_id = CONTEXT_ID.get() if CONTEXT_ID.get() != "N/A" else uuid.uuid4().hex
        metadata.trace_id = trace_id

        with trace_context_manager(trace_id=trace_id, context_id=context_id):
            _LOGGER.debug(f"invoke {method_name}, {request_data}")
            return await invoke_client.async_invoke(method_name, request_data, metadata, timeout_second,request_deserializer, response_deserializer)
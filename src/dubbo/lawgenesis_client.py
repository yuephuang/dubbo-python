import asyncio
import datetime
import os
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from v2.nacos import Instance

from dubbo.client import Client as DubboClient
from dubbo.component.nacos_client import NacosClinet
from dubbo.configcenter.lawgenes_config import LawClientConfig, NotifyConfig
from dubbo.configs import ReferenceConfig
from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.lawgenesis_proto import lawgenesis_pb2, LawMetaData
from dubbo.loggers import loggerFactory
from dubbo.notify import NoticeFactory, ServerMetaData

DEFAULT_MAX_WORKERS = 1000

_LOGGER = loggerFactory.get_logger()


class _InvokeClient:
    def __init__(self, server_name: str, client_config: LawClientConfig, notify_config=None):
        self.client_config = client_config or LawClientConfig()
        self.server_name = server_name
        self._executor = ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS)
        self._urls: Dict[str, DubboClient] = {}
        self.nacos_client = NacosClinet()
        self._initialized = False
        self.notify_config = notify_config or NotifyConfig()
        self._notify_factory: Optional[NoticeFactory] = extensionLoader.get_extension(NoticeFactory, "feishu")()
        self._notify_factory.server_name = server_name
        self._notify_factory.url = self.notify_config.url
        self.weight = {}


    @staticmethod
    def get_authorization() -> lawgenesis_pb2.Auth:
        return lawgenesis_pb2.Auth(
            AUTY="lawgenesis",
            ACID="lawgenesis",
            ACKY="lawgenesis"
        )

    @property
    def client(self) -> str:
        if not self._urls:
            _LOGGER.warning(f"服务 {self.server_name} 实例列表为空，可能正在初始化...")
            self._notify_factory.send_table(title=f"🔴服务调用失败: 服务 {self.server_name} 实例列表为空",
                                                    subtitle=self.server_name,
                                                    elements=[self._get_server_metadata()])
            raise RuntimeError(f"No available instances found for server: {self.server_name}")
        items, weights =  zip(*self.weight.items())
        url_key = random.choices(items, weights=weights, k=1)
        _LOGGER.info(f"调用服务{url_key}")
        return url_key[0]

    def server_key(self, ip, port):
        return f"tri://{ip}:{port}/{self.server_name}"

    def get_service(self, instances: List[Instance] = None):
        instances = instances or self.nacos_client.get_service(server_name=self.server_name)
        weight = {}
        urls = {}
        for instance in instances:
            key = self.server_key(instance.ip, instance.port)
            if key in self._urls:
                urls[key] = self._urls[key]
                weight[key] = self.weight[key]
                continue
            urls[key] = self.connect_client(key)
            weight[key] = 10

        self._urls = urls
        self.weight = weight

    @staticmethod
    def connect_client(url_key):
        return DubboClient(reference=ReferenceConfig.from_url(url=url_key))

    def subscribe(self):
        def cb(instance_list: List[Instance]):
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



    async def async_invoke(self, method_name: str, request_data: any) -> lawgenesis_pb2.LawgenesisReply:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                self._executor,
                self.invoke,
                method_name,
                request_data
            )
            return result
        except Exception as e:
            await self._notify_factory.async_send_table(title="🔴服务调用失败",
                                                        subtitle=common_constants.DEFAULT_SERVER_NAME,
                                                        elements=[self._get_server_metadata(message=e)])
            raise e

    def invoke(self, method_name: str, request_data: any) -> lawgenesis_pb2.LawgenesisReply:
        metadata = LawMetaData(basedata=lawgenesis_pb2.BaseData())
        metadata.data_type = request_data.protobuf_type
        metadata.auth = self.get_authorization()

        law_request = lawgenesis_pb2.LawgenesisRequest(
            DATA=request_data.param2bytes,
            BADA=metadata.basedata
        )
        for _ in range(3):
            url_key = self.client
            client = self._urls[url_key]
            try:
                result = client.unary(
                    method_name=method_name,
                    request_serializer=lawgenesis_pb2.LawgenesisRequest.SerializeToString,
                    response_deserializer=lawgenesis_pb2.LawgenesisReply.FromString,
                )(law_request)
                self.weight[url_key] = min(10, self.weight[url_key] + 1)
                return result
            except Exception as e:
                _LOGGER.error(f"unary {method_name} failed {e}")
                # url_key 降权重
                self.weight[url_key] = max(1, self.weight[url_key] - 1)
                if self.weight[url_key] <= 1:
                    _LOGGER.error(f"unary {method_name} failed {e}, 重新建立客户端")
                    self._urls[url_key] = self.connect_client(url_key)
        raise Exception(f"invokefailed, {self.weight}")



class LawgenesisClient:
    def __init__(self, server_url=None):
        self.__invoke_client: Dict[str, _InvokeClient] = {}
        self.server_url = server_url
        self._loop = None
        self._loop_thread = None

    def select_invoke_client(self, server_name: str, client_config: LawClientConfig = None) -> _InvokeClient:
        if server_name not in self.__invoke_client:
            invoker = _InvokeClient(server_name, client_config)
            invoker.get_service()
            invoker.subscribe()
            self.__invoke_client[server_name] = invoker
        return self.__invoke_client[server_name]

    async def async_invoke(self, server_name, method_name, request_data, client_config: LawClientConfig = None):
        invoke_client = self.select_invoke_client(server_name, client_config)
        return await invoke_client.async_invoke(method_name, request_data)

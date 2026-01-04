import asyncio
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from v2.nacos import Instance

from dubbo.client import Client as DubboClient
from dubbo.component.nacos_client import NacosClinet
from dubbo.configcenter.lawgenes_config import LawClientConfig
from dubbo.configs import ReferenceConfig
from dubbo.constants import common_constants
from dubbo.lawgenesis_proto import lawgenesis_pb2, LawMetaData
from dubbo.loggers import loggerFactory
from dubbo.url import create_url

DEFAULT_MAX_WORKERS = 1000

_LOGGER = loggerFactory.get_logger()


class _InvokeClient:
    def __init__(self, server_name: str, client_config: LawClientConfig):
        self.client_config = client_config or LawClientConfig()
        self.server_name = server_name
        self._executor = ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS)
        self._urls: Dict[str, DubboClient] = {}
        self.nacos_client = NacosClinet()
        self._initialized = False

    @staticmethod
    def get_authorization() -> lawgenesis_pb2.Auth:
        return lawgenesis_pb2.Auth(
            AUTY="lawgenesis",
            ACID="lawgenesis",
            ACKY="lawgenesis"
        )

    @property
    def client(self) -> DubboClient:
        print(f"正在调用服务: {self._urls}")
        if not self._urls:
            _LOGGER.warning(f"服务 {self.server_name} 实例列表为空，可能正在初始化...")
            raise RuntimeError(f"No available instances found for server: {self.server_name}")

        url_key = random.choice(list(self._urls.keys()))
        return self._urls[url_key]

    def server_key(self, ip, port):
        return f"tri://{ip}:{port}/{self.server_name}"

    def get_service(self, instances: List[Instance]=None):
        instances = instances or  self.nacos_client.get_service(server_name=self.server_name)
        urls = {}
        for instance in instances:
            key = self.server_key(instance.ip, instance.port)
            if key in self._urls:
                urls[key] = self._urls[key]
                continue
            urls[key] = DubboClient(reference=ReferenceConfig.from_url(url=create_url(key)))
        self._urls = urls

    def subscribe(self):
        def cb(instance_list: List[Instance]):
            self.get_service(instance_list)


        self.nacos_client.subscribe_service(server_name=self.server_name, group_name=common_constants.GROUP_KEY, listener=cb)

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
            _LOGGER.error(f"异步调用发生错误: {e}")
            raise e

    def invoke(self, method_name: str, request_data: any) -> lawgenesis_pb2.LawgenesisReply:
        metadata = LawMetaData(basedata=lawgenesis_pb2.BaseData())
        metadata.data_type = getattr(request_data, 'protobuf_type', 0)
        metadata.auth = self.get_authorization()

        law_request = lawgenesis_pb2.LawgenesisRequest(
            DATA=request_data.param2bytes if hasattr(request_data, 'param2bytes') else request_data.SerializeToString(),
            BADA=metadata.basedata
        )
        return self.unary(method_name)(law_request)

    def unary(self, method_name: str):
        return self.client.unary(
            method_name=method_name,
            request_serializer=lawgenesis_pb2.LawgenesisRequest.SerializeToString,
            response_deserializer=lawgenesis_pb2.LawgenesisReply.FromString,
        )



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

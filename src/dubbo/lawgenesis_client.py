import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from dubbo import Dubbo
from dubbo.configcenter.lawgenes_config import LawClientConfig
from dubbo.client import Client as DubboClient
from dubbo.configs import ReferenceConfig, RegistryConfig
from dubbo.lawgenesis_proto import lawgenesis_pb2, ProtobufInterface, LawMetaData
from dubbo.url import create_url

DEFAULT_MAX_WORKERS = 1000

class _InvokeClient:
    def __init__(self, server_name, client_config: LawClientConfig, service_url: str= None):
        self.client_config = client_config or LawClientConfig()
        self.server_name = server_name
        self.service_url = service_url
        self._executor = ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS)

    @staticmethod
    def get_authorization() -> lawgenesis_pb2.Auth:
        return lawgenesis_pb2.Auth(
            AUTY="lawgenesis",
            ACID="lawgenesis",
            ACKY="lawgenesis"
        )

    @property
    def client(self) -> DubboClient:
        reference_config = ReferenceConfig(
            service=self.server_name,
            protocol="tri"  # 使用tri协议
        )
        if self.client_config.register_center_url:
            registry_config = RegistryConfig.from_url(self.client_config.register_center_url)
            registry_config.group = self.client_config.client_group
            registry_config.version = self.client_config.version
            registry_config.load_balance = self.client_config.load_balance
            bootstrap = Dubbo(registry_config=registry_config)
            client = bootstrap.create_client(reference_config)
            return client
        if not self.service_url:
            raise Exception("service_url is None")
        url = create_url(self.service_url)
        client = DubboClient(reference=ReferenceConfig.from_url(url=url))
        return client

    async def async_invoke(self, method_name: str, request_data: "ProtobufInterface") -> lawgenesis_pb2.LawgenesisReply:
        """
        使用线程池 (asyncio.to_thread) 运行同步的 self.invoke 方法，
        实现调用侧的异步效果。
        """
        """
                通过线程池异步执行同步的 RPC 调用。
                """
        loop = asyncio.get_event_loop()
        try:
            # 在线程池中执行同步的 _sync_unary_call 方法
            result = await loop.run_in_executor(
                self._executor,
                # 注意：这里需要传递方法名和请求数据作为参数
                self.invoke,
                method_name,
                request_data
            )
            return result
        except Exception as e:
            # logger.error(f"底层Dubbo调用发生错误: {e}") # 假设 logger 存在
            raise e

    def invoke(self, method_name: str, request_data :"ProtobufInterface") -> lawgenesis_pb2.LawgenesisReply:
        metadata = LawMetaData(basedata=lawgenesis_pb2.BaseData())
        metadata.data_type = request_data.protobuf_type
        # metadata.is_cache = True
        metadata.auth = self.get_authorization()
        law_request = lawgenesis_pb2.LawgenesisRequest(
            DATA=request_data.param2bytes,
            BADA=metadata.basedata
        )
        return self.unary(method_name)(law_request)

    def unary(self, method_name) -> lawgenesis_pb2.LawgenesisReply:
        return self.client.unary(method_name=method_name,
                                 request_serializer=lawgenesis_pb2.LawgenesisRequest.SerializeToString,
                                 response_deserializer=lawgenesis_pb2.LawgenesisReply.FromString,
        )

class LawgenesisClient:
    def __init__(self, server_url=None):
        self.__invoke_client : Dict[str, _InvokeClient]= {}
        self.server_url = server_url

    async def async_invoke(self, server_name, method_name, request_data, client_config: LawClientConfig=None):
        if server_name not in self.__invoke_client:
            self.__invoke_client[server_name] = _InvokeClient(server_name, client_config, self.server_url)
        invoke_client = self.__invoke_client[server_name]
        data = await invoke_client.async_invoke(method_name, request_data)
        return data

    def invoke(self, server_name, method_name, request_data, client_config: LawClientConfig=None):
        if server_name not in self.__invoke_client:
            self.__invoke_client[server_name] = _InvokeClient(server_name, client_config, self.server_url)
        invoke_client = self.__invoke_client[server_name]
        data = invoke_client.invoke(method_name, request_data)
        return data

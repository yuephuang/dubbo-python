import asyncio
import logging
import threading
from typing import List

from v2.nacos import NacosNamingService, NacosConfigService, \
    ClientConfigBuilder, GRPCConfig, ConfigParam, RegisterInstanceParam, DeregisterInstanceParam, ListInstanceParam, \
    SubscribeServiceParam, Instance

from dubbo.classes import SingletonBase
from dubbo.constants import common_constants, registry_constants
from dubbo.url import create_url, URL

_LOGGER = logging.getLogger()


class NacosClinet(SingletonBase):
    _loop: asyncio.AbstractEventLoop = None
    _thread: threading.Thread = None
    config_client = None
    naming_client: 'NacosNamingService' = None

    def __init__(self):
        # 初始化时立即启动后台线程
        self._ensure_background_loop()

    @classmethod
    def _ensure_background_loop(cls):
        """确保后台事件循环线程存活"""
        if cls._thread is None or not cls._thread.is_alive():
            cls._loop = asyncio.new_event_loop()
            cls._thread = threading.Thread(
                target=cls._run_event_loop,
                args=(cls._loop,),
                name="NacosBackgroundThread",
                daemon=True
            )
            cls._thread.start()
            _LOGGER.info("Nacos background event loop started.")

    @staticmethod
    def _run_event_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _submit_to_loop(self, coro):
        """核心工具：将协程提交到后台 Loop 并同步等待结果"""
        if self._loop is None:
            raise RuntimeError("Nacos event loop is not running")

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            # 阻塞调用线程直到任务完成，并返回结果
            return future.result()
        except Exception as e:
            _LOGGER.error(f"Error executing task in Nacos background loop: {e}")
            raise

    @classmethod
    async def _internal_init(cls):
        """
        必须在后台 Loop 内部执行的初始化逻辑。
        这样 gRPC 的底层连接和 Task 才会绑定到后台 Loop。
        """
        if all([cls.naming_client, cls.config_client]):
            return

        _client_config = ClientConfigBuilder() \
            .server_address(common_constants.NACOS_ADDRESS) \
            .namespace_id(common_constants.NACOS_NAMESPACE_ID) \
            .username(common_constants.NACOS_USER) \
            .password(common_constants.NACOS_PASSWORD) \
            .cache_dir(common_constants.NACOS_CACHE) \


        client_config = _client_config.build()
        grpc_config = GRPCConfig()
        client_config.grpc_config = grpc_config

        # 关键点：在当前 loop 创建 service
        cls.config_client = await NacosConfigService.create_config_service(client_config=client_config)
        cls.naming_client = await NacosNamingService.create_naming_service(client_config)
        _LOGGER.info("NacosNamingService and ConfigService initialized in background loop.")

    # --- 配置服务 (Config Service) 接口 ---

    def get_config(self, config_name: str, group: str):
        async def _task():
            await self._internal_init()
            return await self.config_client.get_config(ConfigParam(data_id=config_name, group=group))

        return self._submit_to_loop(_task())

    def publish_config(self, config_name: str, group: str, content: str):
        async def _task():
            await self._internal_init()
            return await self.config_client.publish_config(
                ConfigParam(data_id=config_name, group=group, content=content)
            )

        return self._submit_to_loop(_task())

    def subscribe_config(self, config_name: str, group: str, listener):
        async def _task():
            await self._internal_init()
            await self.config_client.add_listener(listener=listener, data_id=config_name, group=group)

        return self._submit_to_loop(_task())

    # --- 注册中心服务 (Naming Service) 接口 ---

    def register_service(self, url: URL):
        """
        新起线程处理注册，调用者无需 await，无需维护 while True
        """

        async def _task():
            await self._internal_init()
            _LOGGER.info(f"Registering service to Nacos: {url.host}:{url.port}")
            return await self.naming_client.register_instance(
                request=RegisterInstanceParam(
                    service_name=common_constants.DEFAULT_SERVER_NAME,
                    group_name=common_constants.GROUP_KEY,
                    ip=url.host, port=url.port, weight=1.0,
                    cluster_name=common_constants.CLUSTER_KEY,
                    metadata=common_constants.NACOS_METAINFO,
                    enabled=True,
                    healthy=True,
                    ephemeral=True
                )
            )

        return self._submit_to_loop(_task())

    def unregister_service(self, url: URL):
        async def _task():
            await self._internal_init()
            return await self.naming_client.deregister_instance(
                DeregisterInstanceParam(
                    service_name=common_constants.DEFAULT_SERVER_NAME,
                    group_name=common_constants.GROUP_KEY,
                    ip=url.host, port=url.port,
                    cluster_name=common_constants.CLUSTER_KEY,
                    ephemeral=True
                )
            )

        return self._submit_to_loop(_task())

    def get_service(self, server_name: str, group_name: str = None, cluster_name: str = None) -> List[Instance]:
        async def _task():
            await self._internal_init()
            return await self.naming_client.list_instances(
                ListInstanceParam(
                    service_name=server_name,
                    group_name=group_name or common_constants.GROUP_KEY,
                    healthy_only=True,
                    subscribe=False,
                    clusters=[cluster_name or common_constants.CLUSTER_KEY]
                )
            )

        return self._submit_to_loop(_task())

    def subscribe_service(self, server_name: str, group_name: str, listener):
        async def _task():
            await self._internal_init()
            await self.naming_client.subscribe(
                SubscribeServiceParam(
                    service_name=server_name,
                    group_name=group_name or common_constants.GROUP_KEY,
                    clusters=[common_constants.CLUSTER_KEY],
                    subscribe_callback=listener
                )
            )

        return self._submit_to_loop(_task())

    def shutdown(self):
        """彻底关闭并停止线程"""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=2)
            _LOGGER.info("Nacos background thread shutdown.")

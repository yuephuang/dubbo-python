import asyncio
from typing import Union

from v2.nacos import ClientConfigBuilder, GRPCConfig, NacosConfigService, NacosNamingService, NacosConfigService, \
    ClientConfigBuilder, GRPCConfig, ConfigParam, RegisterInstanceParam, DeregisterInstanceParam, ListInstanceParam, \
    SubscribeServiceParam

from dubbo.classes import SingletonBase
from dubbo.url import create_url, URL
from dubbo.constants import common_constants, registry_constants


class NacosClinet(SingletonBase):
    def __init__(self):
        self.config_client = None
        self.naming_client : 'NacosNamingService' = None
        try:
            self._init_task = asyncio.create_task(self.start_init())
        except RuntimeError:
            # 如果没有运行中的事件循环，则运行它
            asyncio.run(self.start_init())
        except Exception as e:
            raise RuntimeError(f"Failed to initialize NacosConfigService: {e}")
    
    async def start_init(self):
        url = create_url(common_constants.NACOS_URL)
        server_address = f"{url.host}:{url.port if url.port else 8848}"
        parameters = url.parameters

        # 构建客户端配置
        client_config = ClientConfigBuilder() \
            .server_address(server_address) \
            .namespace_id(parameters.get(registry_constants.NAMESPACE_KEY)) \
            .username(url.username) \
            .password(url.password) \
            .build()

        # 检查是否提供了 endpoint，如果提供了则设置
        endpoint = parameters.get("endpoint")
        if endpoint:
            # v2 客户端可能支持更细粒度的配置，这里以 URL 中的参数为准
            client_config.set_endpoint(endpoint)

        # 创建 GRPC 配置（使用默认配置）
        grpc_config = GRPCConfig()
        client_config.grpc_config = grpc_config
        # 初始化 NacosConfigService 实例
        config_client = await NacosConfigService.create_config_service(client_config=client_config)
        naming_client = await NacosNamingService.create_naming_service(client_config)
        
        self.naming_client = naming_client
        self.config_client = config_client


    ### 配置服务 ###
    async def async_get_config(self, config_name: str, group: str):
        """
        异步获取配置内容
        """
        if self._init_task:
            await self._init_task
        content = await self.config_client.get_config(ConfigParam(
            data_id=config_name,
            group=group
        ))
        return content

    async def async_publish_config(self, config_name, group, content):
        """
        异步发布或更新配置
        """
        if self._init_task:
            await self._init_task
        res = await self.config_client.publish_config(
            ConfigParam(
            data_id=config_name,
            group=group,
            content=content
            )
        )
        return res

    async def async_remove_config(self, config_name: str, group: str):
        """
        异步删除配置
        """
        if self._init_task:
            await self._init_task
        res = await self.config_client.remove_config(
            ConfigParam(
                data_id=config_name,
                group=group
            )
        )
        return res

    async def async_subscribe_config(self, config_name, group, listener):
        """
        异步订阅配置变更
        """
        if self._init_task:
            await self._init_task
        await self.config_client.add_listener(
            listener=listener,
            data_id=config_name,
            group=group
        )

    async def async_unsubscribe_config(self, config_name, group, listener):
        """
        异步取消订阅
        """
        if self._init_task:
            await self._init_task
        # 尝试使用 v2 客户端的 unsubscribe 方法
        await self.config_client.remove_listener(
            listener=listener,
            data_id=config_name,
            group=group
        )

    async def async_close_config(self):
        """
        关闭客户端，停止订阅
        """
        if self._init_task:
            await self._init_task
        await  self.config_client.shutdown()

    ### 注册中心服务 ###
    async def async_register_service(self, url: URL):
        response = await self.naming_client.register_instance(
            request=RegisterInstanceParam(service_name=common_constants.DEFAULT_SERVER_NAME,
                                          group_name=common_constants.GROUP_KEY,
                                          ip=url.host, port=url.port, weight=1.0,
                                          cluster_name=common_constants.CLUSTER_KEY,
                                          metadata=common_constants.NACOS_METAINFO,
                                          enabled=True,
                                          healthy=True, ephemeral=True))

        return response

    async def async_unregister_service(self, url: URL):
        response = await self.naming_client.deregister_instance(
            DeregisterInstanceParam(service_name=common_constants.DEFAULT_SERVER_NAME, group_name=common_constants.GROUP_KEY,
            ip=url.host, port=url.port, cluster_name=common_constants.CLUSTER_KEY, ephemeral=True))
        return response

    async def async_get_service(self):
        """
        异步获取服务列表
        """
        if self._init_task:
            await self._init_task
        response = await self.naming_client.list_instances(
            ListInstanceParam(
                service_name=common_constants.DEFAULT_SERVER_NAME, group_name=common_constants.GROUP_KEY,
                healthy_only=True,
                subscribe=True,
                clusters=[common_constants.CLUSTER_KEY]
            ))
        return response

    async def async_subscribe_service(self, listener):
        """
        异步订阅服务列表
        """
        await self.naming_client.subscribe(
            SubscribeServiceParam(service_name=common_constants.DEFAULT_SERVER_NAME,
                                  group_name=common_constants.GROUP_KEY, subscribe_callback=listener))

    async def async_unsubscribe_service(self, listener):
        """
        异步取消订阅
        """
        await self.naming_client.unsubscribe(
            SubscribeServiceParam(service_name=common_constants.DEFAULT_SERVER_NAME,
                                    group_name=common_constants.GROUP_KEY,
                                    subscribe_callback=listener))

#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncio
from typing import Union

# 移除旧的 nacos 客户端，并导入 v2 版本配置服务所需的类
from v2.nacos import NacosConfigService, ClientConfigBuilder, GRPCConfig, ConfigParam

from dubbo.configcenter._interfaces import Config
from dubbo.constants import registry_constants
from dubbo.url import create_url, URL

__all__ = ["NacosConfigCenter"]

class NacosConfigCenter(Config):
    """
    Nacos 配置中心实现，使用 v2.nacos.NacosConfigService
    """

    def __init__(self, url: Union[str, URL]):
        if isinstance(url, str):
            url = create_url(url)
        self.url = url
        self.nacos_client = None
        self._init_task = None
        try:
            self._init_task = asyncio.create_task(self._init_nacos_client())
        except RuntimeError:
            # 如果没有运行中的事件循环，则运行它
            asyncio.run(self._init_nacos_client())

    async def _init_nacos_client(self) -> NacosConfigService:
        """
        根据 URL 参数初始化 v2 版本的 NacosConfigService 客户端
        """
        # 提取服务器地址和端口，默认端口为 8848
        server_address = f"{self.url.host}:{self.url.port if self.url.port else 8848}"
        parameters = self.url.parameters

        # 构建客户端配置
        client_config = ClientConfigBuilder() \
            .server_address(server_address) \
            .namespace_id(parameters.get(registry_constants.NAMESPACE_KEY)) \
            .username(self.url.username) \
            .password(self.url.password) \
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
        client = await NacosConfigService.create_config_service(
            client_config=client_config
        )
        self.nacos_client = client


    async def async_get_config(self, config_name: str, group: str):
        """
        异步获取配置内容
        """
        if self._init_task:
            await self._init_task
        content = await self.nacos_client.get_config(ConfigParam(
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
        res = await self.nacos_client.publish_config(
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
        res = await self.nacos_client.remove_config(
            ConfigParam(
                data_id=config_name,
                group=group
            )
        )
        return res

    async def async_subscribe(self, config_name, group, listener):
        """
        异步订阅配置变更
        """
        if self._init_task:
            await self._init_task
        await self.nacos_client.add_listener(
            listener=listener,
            data_id=config_name,
            group=group
        )

    async def async_unsubscribe(self, config_name, group, listener):
        """
        异步取消订阅
        """
        if self._init_task:
            await self._init_task
        # 尝试使用 v2 客户端的 unsubscribe 方法
        await self.nacos_client.remove_listener(
            listener=listener,
            data_id=config_name,
            group=group
        )

    async def async_close(self):
        """
        关闭客户端，停止订阅
        """
        if self._init_task:
            await self._init_task
        await  self.nacos_client.shutdown()

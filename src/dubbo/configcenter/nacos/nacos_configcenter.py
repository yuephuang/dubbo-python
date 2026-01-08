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

# 移除旧的 nacos 客户端，并导入 v2 版本配置服务所需的类

from dubbo.component.nacos_client import NacosClinet
from dubbo.configcenter._interfaces import Config

__all__ = ["NacosConfigCenter"]


class NacosConfigCenter(Config):
    """
    Nacos 配置中心实现，使用 v2.nacos.NacosConfigService
    """

    def __init__(self):
        self.nacos_client = NacosClinet()

    async def async_get_config(self, config_name: str, group: str):
        """
        异步获取配置内容
        """
        content = await self.nacos_client.async_get_config(config_name, group)
        return content

    async def async_publish_config(self, config_name, group, content):
        """
        异步发布或更新配置
        """
        return await self.nacos_client.async_publish_config(
            config_name=config_name,
            group=group,
            content=content
        )

    async def async_remove_config(self, config_name: str, group: str):
        """
        异步删除配置
        """
        return await self.nacos_client.async_remove_config(
            config_name=config_name,
            group=group
        )

    async def async_subscribe(self, config_name, group, listener):
        """
        异步订阅配置变更
        """
        await self.nacos_client.async_subscribe_config(
            config_name=config_name,
            group=group,
            listener=listener
        )

    async def async_unsubscribe(self, config_name, group, listener):
        """
        异步取消订阅
        """
        return await self.nacos_client.async_unsubscribe_config(
            config_name=config_name,
            group=group,
            listener=listener
        )

    async def async_close(self):
        """
        关闭客户端，停止订阅
        """
        return await self.nacos_client.async_close_config()

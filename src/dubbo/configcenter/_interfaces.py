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
import abc
import asyncio


class Config(abc.ABC):
    @abc.abstractmethod
    async def async_get_config(self, config_name: str, group: str):
        """
        get config
        获取配置信息
        :param: config_name: 配置名称
        :param: group: 分组
        """
        pass

    @abc.abstractmethod
    async def async_publish_config(self, config_name, group, content):
        """
        Put config
        发布配置信息
        :param: config_name: 配置名称
        :param: group: 分组
        :param: content: 配置信息
        """
        pass

    @abc.abstractmethod
    async def async_remove_config(self, config_name: str, group: str):
        """
        Remove config
        删除配置信息
        :param: config_name: 配置名称
        :param: group: 分组
        """
        pass


    @abc.abstractmethod
    async def async_subscribe(self, config_name, group, listener):
        """
        Add listener
        添加监听器
        :param: config_name: 配置名称
        :param: group: 分组
        :param: listener: 监听器
        """
        pass


    @abc.abstractmethod
    async def async_unsubscribe(self, config_name, group, listener):
        """
        Remove listener
        删除监听器
        :param: config_name: 配置名称
        :param: group: 分组
        :param: listener: 监听器
        """
        pass

    @abc.abstractmethod
    async def async_close(self):
        """
        Close
        关闭
        """
        pass


    def get_config(self, config_name: str, group: str):
        """
        get config
        获取配置信息
        :param: config_name: 配置名称
        :param: group: 分组
        """
        asyncio.run(self.async_get_config(config_name, group))

    def publish_config(self, config_name, group, content):
        """
        Put config
        发布配置信息
        :param: config_name: 配置名称
        :param: group: 分组
        :param: content: 配置信息
        """
        asyncio.run(self.async_publish_config(config_name, group, content))

    def remove_config(self,  config_name: str, group: str):
        """
        Remove config
        删除配置信息
        :param: config_name: 配置名称
        :param: group: 分组
        """
        asyncio.run(self.async_remove_config(config_name, group))


    def subscribe(self, config_name, group, listener):
        """
        Add listener
        添加监听器
        :param: config_name: 配置名称
        :param: group: 分组
        :param: listener: 监听器
        """
        asyncio.run(self.async_subscribe(config_name, group, listener))


    def unsubscribe(self, config_name, group, listener):
        """
        Remove listener
        删除监听器
        :param: config_name: 配置名称
        :param: group: 分组
        :param: listener: 监听器
        """
        asyncio.run(self.async_unsubscribe(config_name, group, listener))


    def close(self):
        """
        Close
        关闭
        """
        asyncio.run(self.async_close())
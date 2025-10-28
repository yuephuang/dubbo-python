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
import ast
import asyncio
import logging
import os
from abc import ABC

from dubbo.configcenter import NacosConfigCenter

_LOGGER = logging.getLogger(__name__)

class ConfigReloader(ABC):
    """
    配置重载器基类。
    实现此类的子类在实例化时会自动订阅 Nacos 配置。
    """

    @abc.abstractmethod
    def config_name(self) -> str:
        """
        获取 Nacos 的 Data ID。
        """

    @abc.abstractmethod
    def group(self) -> str:
        """
        获取 Nacos 的 Group。
        """

    @staticmethod
    def nacos_client() -> NacosConfigCenter:
        """
        获取 Nacos 配置中心客户端实例。
        注意: NacosConfigCenter.__init__ 内部已经阻塞地完成了异步客户端的初始化。
        """
        return NacosConfigCenter(url=os.environ.get("NACOS_CONFIG_URL"))

    @classmethod
    async def reload(cls, tenant, data_id, group, content):
        """
        异步重载配置。
        订阅的格式一定是个字典。
        """
        try:
            _LOGGER.info(f"Reload config from nacos: {tenant}/{data_id}/{group}")
            # 使用 ast.literal_eval 安全地将字符串转换为 Python 对象 (通常是字典)
            data_json = ast.literal_eval(content)

            if not isinstance(data_json, dict):
                _LOGGER.error(f"Reload config: Content is not a dictionary, failed. Content: {content}")
                return

            _LOGGER.info(f"Reload config: {data_json}, success")

        except Exception as e:
            _LOGGER.error(f"Reload config: {content}, failed: {e}")
            return

        cls.update_cls(data_json=data_json)

    @classmethod
    def update_cls(cls, data_json: dict):
        # 遍历配置字典，更新类属性
        for key, value in data_json.items():
            # 暂时全部更新
            # if key not in cls.__annotations__:
            #     continue
            try:
                setattr(cls, key, value)
                _LOGGER.info(f"Updated config: {cls.__name__}.{key} = {value}")
            except AttributeError:
                # 捕获没有 set_config 方法的错误
                _LOGGER.error(f"Config field {cls.__name__}.{key} does not have set_config method. Value: {value}")
            except Exception as e:
                _LOGGER.error(f"Error setting config for {cls.__name__}.{key}: {e}")

    def _subscribe_config(self):
        """
        实例创建后执行配置订阅的逻辑。
        """
        config_name = self.config_name()
        group = self.group()

        # 初始化获取配置
        data = asyncio.run(self.nacos_client().async_get_config(
            config_name=config_name,
            group=group
        ))
        self.update_cls(data_json=ast.literal_eval(data))

        # 定义配置变更监听器
        try:
            # 阻塞地运行异步订阅任务
            asyncio.run(self.nacos_client().async_subscribe(
                config_name=config_name,
                group=group,
                listener=self.reload
            ))
            _LOGGER.info(f"Successfully subscribed to Nacos config: {config_name}/{group}")
        except Exception as e:
            _LOGGER.error(f"Failed to subscribe to Nacos config: {config_name}/{group}. Error: {e}")

    def __new__(cls, *args, **kwargs):
        # 1. 创建实例
        instance = super().__new__(cls)

        # 2. 调用实例方法执行订阅
        # 放在 __new__ 中可以确保订阅逻辑在 __init__ 执行之前完成
        instance._subscribe_config()

        return instance

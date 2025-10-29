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
import datetime
import os
import subprocess
import threading
import time
from typing import Optional

from dubbo.bootstrap import Dubbo
from dubbo.configs import ServiceConfig
from dubbo.constants import common_constants
from dubbo.extension import extensionLoader
from dubbo.notify import NoticeFactory, ServerNotifyData
from dubbo.protocol import Protocol
from dubbo.registry.protocol import RegistryProtocol
from dubbo.url import URL


class Server:
    """
    Dubbo Server
    """

    def __init__(self, service_config: ServiceConfig, dubbo: Optional[Dubbo] = None):
        self._initialized = False
        self._global_lock = threading.RLock()

        self._service = service_config
        self._dubbo = dubbo or Dubbo()

        self._protocol: Optional[Protocol] = None
        self._url: Optional[URL] = None
        self._exported = False
        self._start = False
        self.notify_factory: Optional[NoticeFactory] = None
        # initialize the server
        self._initialize()

    def _initialize(self):
        """
        Initialize the server.
        """
        with self._global_lock:
            if self._initialized:
                return

            # get the protocol
            service_protocol = extensionLoader.get_extension(Protocol, self._service.protocol)()

            registry_config = self._dubbo.registry_config

            self._protocol = (
                RegistryProtocol(registry_config, service_protocol) if self._dubbo.registry_config else service_protocol
            )

            # build url
            service_url = self._service.to_url()
            if registry_config:
                self._url = registry_config.to_url().copy()
                self._url.attributes[common_constants.EXPORT_KEY] = service_url
                for k, v in service_url.attributes.items():
                    self._url.attributes[k] = v
            else:
                self._url = service_url

            self.notify_factory: NoticeFactory = extensionLoader.get_extension(NoticeFactory, "feishu")(url=os.environ.get("notify_url"))
            self.notify_factory.server_name = self._service.service_handler.service_name

    @property
    def intranet_ip(self):
        try:
            # 目标命令：'ip route show dev eth0'
            # 输出示例：default via 192.168.1.1 dev eth0
            interface = "eth0"
            command = f"ip route show dev {interface}"
            result = subprocess.run(
                command,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            output_lines = result.stdout.strip().split('\n')

            for line in output_lines:
                # 寻找包含 'default via' 的行
                if 'default via' in line:
                    parts = line.split()
                    try:
                        # 'default' [0], 'via' [1], '192.168.1.1' [2]
                        gateway_ip = parts[2]
                        return gateway_ip
                    except IndexError:
                        return f"解析 '{interface}' 路由输出失败。"

            return f"在 '{interface}' 的路由表中未找到默认网关。"

        except subprocess.CalledProcessError as e:
            return f"No intranet_ip  found, {e} "
        except Exception as e:
            return f"No intranet_ip  found, {e}"

    @property
    def internet_ip(self):
        try:
            # 获取公网 IP
            command = "curl ifconfig.me"
            result = subprocess.run(
                command,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return result.stdout.strip()

        except subprocess.CalledProcessError as e:
            return f"No Internet IP found. {e}"

    def start(self):
        """
        Start the server.
        """
        server_data = ServerNotifyData(
            server_name=self._service.service_handler.service_name,
            host=self._url.host,
            port=self._url.port,
            intranet_ip=self.intranet_ip,
            internet_ip=self.internet_ip,
            status="start",
            start_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        server_notify_data = ServerNotifyData(server_name="test", status="进行中",
                                              start_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                              host="127.0.0.1", port=8080, intranet_ip="127.0.0.1",
                                              internet_ip="127.0.0.1")

        asyncio.run(self.notify_factory.send_table(
            title=f"服务 {self._service.service_handler.service_name}",
            subtitle="服务启动",
            elements=[server_notify_data]
        ))
        self._start = True
        with self._global_lock:
            while self._start:
                if self._exported:
                    return

                self._protocol.export(self._url)
                time.sleep(1)


                self._exported = True
        self.notify_factory.send_table(
            title=f"服务 {self._service.service_handler.service_name}",
            subtitle="服务停止",
            elements=[server_data]
        )

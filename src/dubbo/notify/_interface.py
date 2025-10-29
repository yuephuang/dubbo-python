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
import threading
import uuid
from abc import ABC
from typing import Dict, List

from aiohttp import ClientSession

from dubbo.loggers import loggerFactory

_LOGGER = loggerFactory.get_logger()

class ServerNotifyData(object):
    """
    服务状态数据
    """
    def __init__(self, server_name, host, port, intranet_ip, internet_ip, status, start_time):
        self.server_name = server_name
        self.host = host
        self.port = str(port)
        self.intranet_ip = intranet_ip
        self.internet_ip = internet_ip
        self.status = status
        self.start_time = start_time
        self.uuid = uuid.uuid4().hex

    @property
    def json(self):
        return {
            "server_name": self.server_name,
            "host": self.host,
            "port": self.port,
            "intranet_ip": self.intranet_ip,
            "internet_ip": self.internet_ip,
            "status": self.status,
            "start_time": self.start_time,
            "uuid": self.uuid
        }


class NoticeFactory(ABC):
    """
    A factory class to create notice.
    """
    _instance = {}
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """
        Create a notice.
        :param args: The arguments to pass to the notice.
        :param kwargs: The keyword arguments to pass to the notice.
        :return: The notice.
        """
        if cls._instance.get(kwargs.get("url")) is None:
            with cls._instance_lock:
                cls._instance[kwargs.get("url")] = super().__new__(cls)
        return cls._instance[kwargs.get("url")]

    def __init__(self, url: str, header: Dict[str, str] = None, server_name: str="dubbo-server"):
        """
        Initialize the notice.
        :param url: The url of the notice.
        :param header: str
        :param server_name: server_name
        """
        self._url = url
        self._server_name = server_name
        self._header = header or {}
        self._timeout = 60

    @property
    def url(self):
        """
        Get the url.
        :return: The url.
        """
        return self._url

    @url.setter
    def url(self, url):
        """
        Set the url.
        :param url: The url.
        """
        self._url = url

    @property
    def header(self):
        """
        Get the header.
        :return: The header.
        """
        return self._header

    @header.setter
    def header(self, header):
        """
        Set the header.
        :param header: The header.
        """
        self._header = header

    @property
    def server_name(self):
        """
        Get the server name.
        :return: The server name.
        """
        return self._server_name

    @server_name.setter
    def server_name(self, server_name):
        """
        Set the server name.
        :param server_name: The server name.
        """
        self._server_name = server_name

    @property
    def timeout(self):
        """
        Get the timeout.
        :return: The timeout.
        """
        return self._timeout

    @timeout.setter
    def timeout(self, timeout):
        """
        Set the timeout.
        :param timeout: The timeout.
        """
        self._timeout = timeout


    async def async_send_data(self, content: dict):
        try:
            async with ClientSession() as session:
                async with session.post(self.url, json=content,
                                        headers=self.header,
                                        timeout=self.timeout,
                                        ssl=False,
                                        ) as response:
                    response.raise_for_status()
                    data = await response.json()
            return data
        except Exception as e:
            _LOGGER.error(f"Send data to {self.url} failed: {e}")
            # 通知不报错

    @abc.abstractmethod
    async def send_text(self, text):
        """
        Send data to the notice.
        :param text: The content to send.
        :return: The response.
        """

    @abc.abstractmethod
    async def send_rich_text(self, title, content: List[List[Dict[str, str]]]):
        """

        """


    async def send_table(self, title="", subtitle="", elements: List[ServerNotifyData] =None):
        """
        Send data to the notice.
        :param title: The title of the notice.
        :param subtitle: The subtitle of the notice.
        :param elements: The elements of the notice.
        :return: The response.
        """
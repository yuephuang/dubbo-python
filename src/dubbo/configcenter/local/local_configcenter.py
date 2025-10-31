import asyncio
import hashlib
import os
import tomllib

import orjson

from dubbo.configcenter._interfaces import Config


class _LocalLister(object):
    """
    本地配置监听器
    """
    def __init__(self, url: str, config_name, listener):
        self.url = url
        self.last_md5 = None
        self.config_name = config_name
        self.listener = listener
        self.listen_loop = True
        asyncio.create_task(self.async_listener())

    async def async_listener(self):
        while self.listen_loop:
            content =  tomllib.load(open(self.url, "rb")).get(self.config_name)
            md5 = hashlib.md5(orjson.dumps(content)).hexdigest()
            if md5 != self.last_md5:
                self.last_md5 = md5
                await self.listener("", "", "", content)
            await asyncio.sleep(30)


class LocalConfigCenter(Config):
    """
    本地配置中心实现，使用本地文件系统作为配置存储
    """
    def __init__(self, url: str):
        self.url = url
        if not os.path.exists(self.url):
            raise Exception("url is not exists")
        if not url.endswith(".toml"):
            raise Exception("url is not toml")
        self.configs = tomllib.load(open(self.url, "rb"))
        # 校验文件是否有变化
        self._listeners = {}


    async def async_get_config(self, config_name: str, group: str):
        return self.configs.get(config_name)

    async def async_remove_config(self, config_name: str, group: str):
        raise Exception("not support")

    async def async_publish_config(self, config_name, group, content):
        raise Exception("not support")

    async def async_subscribe(self, config_name, group, listener):
        _local_listener = _LocalLister(self.url, config_name, listener)
        self._listeners[(config_name, group)] = _local_listener

    async def async_unsubscribe(self, config_name, group, listener):
        _local_listener = self._listeners.get((config_name, group))
        if _local_listener:
            _local_listener.listen_loop = False
        self._listeners.pop((config_name, group), None)

    async def async_close(self):
        for listener in self._listeners.values():
            listener.listen_loop = False
        self._listeners.clear()
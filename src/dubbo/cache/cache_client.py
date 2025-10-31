#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author:      huangyuepeng
@Project:     dubbo-demo
@File:        client.py
@Description: 
@Create Date: 2025/7/7 17:26
"""

from dubbo.cache.local_cache import LocalCacheClient
from dubbo.configcenter.lawgenes_config import MethodCacheConfig


class CacheClient:
    def __init__(self, cache_config: MethodCacheConfig):
        self.cache_config = cache_config
        self.client = LocalCacheClient(cache_config)

    def get(self, cache_key: str):
        if not self.cache_config.cache_enable:
            return None
        return self.client.get(cache_key)

    def set(self, cache_key: str, result):
        """
        缓存数据
        Args:
            cache_key: 缓存的key，一般是方法名+参数
            result: 缓存的结果

        Returns:

        """
        if not self.cache_config.cache_enable:
            return None
        return self.client.set(cache_key, result)

    def clear(self):
        """
        Args:
        Returns:

        """
        if self.cache_config.cache_enable:
            self.client.clear()

    def delete_key(self, cache_key: str):
        """
        删除指定缓存key
        Args:
            cache_key: 缓存key

        Returns:

        """
        if self.cache_config.cache_enable:
            self.client.delete_key(cache_key)

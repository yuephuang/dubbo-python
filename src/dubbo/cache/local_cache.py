#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author:      huangyuepeng
@Project:     dubbo-demo
@File:        local.py
@Description: 
@Create Date: 2025/7/7 17:25
"""
from datetime import timedelta, datetime
import threading # <-- 导入 threading 模块

from cachetools import TLRUCache
from pympler import asizeof

from dubbo.configcenter.lawgenes_config import MethodCacheConfig


def datetime_ttu(_key, value, now):
    # assume now to be of type datetime.datetime, and
    # value.hours to contain the item's time-to-use in hours
    return datetime + timedelta(seconds=value.hours)

class LocalCacheClient:
    def __init__(self, cache_config: MethodCacheConfig):
        def dynamic_ttl(key, value, now):
            ttl_in_seconds = cache_config.cache_ttl
            return now + timedelta(seconds=ttl_in_seconds)

        self._cache = TLRUCache(maxsize=cache_config.cache_memory_size, ttu=dynamic_ttl,
                                timer=datetime.now, getsizeof=asizeof.asizeof)
        self._lock = threading.Lock() # <-- 创建一个锁

    def get(self, cache_key: str):
        with self._lock: # <-- 使用锁保护
            return self._cache.get(cache_key, None)

    def set(self, cache_key: str, result):
        with self._lock: # <-- 使用锁保护
            self._cache[cache_key] = result

    def clear(self):
        with self._lock: # <-- 使用锁保护
            self._cache.clear()

    def delete_key(self, cache_key: str):
        with self._lock: # <-- 使用锁保护
            self._cache.pop(cache_key, None)
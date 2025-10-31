import abc
import ast
import asyncio
import os
import time
from typing import Union, Dict, Any

import cachetools

from dubbo.loggers import loggerFactory

from dubbo.configcenter import NacosConfigCenter, LocalConfigCenter, Config

_LOGGER = loggerFactory.get_logger()


class ConfigReloader:
    """
    配置重载器基类。
    配置的初始化和订阅逻辑已被移至 async_start_reloader 方法，
    必须在程序启动的异步事件循环中调用此方法。
    """

    # 实现客户端单例缓存
    _client_instance: "Config" = None
    def __init__(self):
        """Initializes a ConfigReloader instance.
        """
        # 注意：此处的 _cache_config 是一个静态变量，用于缓存配置。
        # 初始化获取配置
        self._group = "config"
        self._config_name = ""
        self._cache_config = {}

    @property
    def config_name(self) -> str:
        """
        获取 Nacos 的 Data ID。
        """
        return self._config_name

    @config_name.setter
    def config_name(self, value: str):
        """
        设置 Nacos 的 Data ID。
        """
        self._config_name = value

    @property
    def config_group(self) -> str:
        """
        获取 Nacos 的 Group。
        """
        return self._group

    @config_group.setter
    def config_group(self, value: str):
        """
        设置 Nacos 的 Group。
        """
        self._group = value

    @classmethod
    def client(cls) -> "Config":
        """
        获取 Nacos 配置中心客户端实例 (惰性单例)。
        确保在整个应用生命周期内只创建一个客户端实例。
        """
        if cls._client_instance is None:
            # 根据环境变量创建客户端实例
            if os.environ.get("config_type", "local") == "local":
                cls._client_instance = LocalConfigCenter(url=os.environ.get("CONFIG_URL"))
            else:
                cls._client_instance = NacosConfigCenter(url=os.environ.get("CONFIG_URL"))
        return cls._client_instance

    async def reload(self, tenant, data_id, group, content):
        """
        异步重载配置。
        订阅的格式一定是个字典。
        """
        try:
            _LOGGER.info(f"Reload config from nacos: {tenant}/{data_id}/{group}")
            # 使用 ast.literal_eval 安全地将字符串转换为 Python 对象 (通常是字典)
            # 注意: 如果配置内容非常大，ast.literal_eval 可能会消耗一定 CPU，但通常不是高负载的主要原因。
            if not isinstance(content, dict):
                data_json = ast.literal_eval(content)
            else:
                data_json = content

            if not isinstance(data_json, dict):
                _LOGGER.error(f"Reload config: Content is not a dictionary, failed. Content: {content}")
                return

            _LOGGER.info(f"Reload config: {data_json}, success")

        except Exception as e:
            _LOGGER.error(f"Reload config: {content}, failed: {e}")
            return

        # 更新缓存
        self._cache_config = data_json
        self.update_cls()

    def update_cls(self):
        # 遍历配置字典，更新类实例属性
        for key, value in self._cache_config.items():
            # 仅更新 __init__ 中已声明的属性，避免动态添加未预期的属性
            if key not in self.__dict__:
                _LOGGER.warning(
                    f"Config field '{self.__class__.__name__}.{key}' not defined in __init__, skipping update.")
                continue

            try:
                # 假设这里可以直接设置属性，不需要 set_config 方法
                setattr(self, key, value)
                _LOGGER.info(f"Updated config: {self.__class__.__name__}.{key} = {value}")
            except Exception as e:
                # 捕获其他设置属性时可能发生的错误
                _LOGGER.error(f"Error setting config for {self.__class__.__name__}.{key}: {e}")

    async def async_start_reloader(self):
        """
        异步启动配置重载器：获取初始配置并设置非阻塞的订阅监听。
        """
        config_name = self.config_name
        group = self.config_group
        client = self.client()  # 现在获取的是单例实例

        _LOGGER.info(f"Starting initial config fetch for: {config_name}/{group}")

        # 1. 初始化获取配置 (非阻塞)
        data = await client.async_get_config(
            config_name=config_name,
            group=group
        )

        # 检查并处理数据格式
        if not isinstance(data, dict):
            try:
                data = ast.literal_eval(data)
            except Exception as e:
                _LOGGER.error(f"Initial config fetch failed to parse content: {data}. Error: {e}")
                return
        self._cache_config = data
        self.update_cls()
        _LOGGER.info(f"Initial config loaded successfully: {config_name}/{group}")

        # 2. 定义配置变更监听器 (非阻塞订阅)
        try:
            # 异步地设置订阅，这个 await 应该会立即返回，而订阅任务在后台运行
            await client.async_subscribe(
                config_name=config_name,
                group=group,
                listener=self.reload
            )
            _LOGGER.info(f"Successfully subscribed to Nacos config: {config_name}/{group}")
        except Exception as e:
            # 订阅失败不应阻塞应用启动
            _LOGGER.error(f"Failed to subscribe to Nacos config: {config_name}/{group}. Error: {e}")


class LawServerConfig(ConfigReloader):
    """
    服务配置类
    """
    def __init__(self):
        """Initializes a ServerConfig instance.
        """
        super().__init__()
        self.name = None
        self.version = None
        self.host = None
        self.port = None
        self.server_group = None
        self.env = None
        self.register_center_url = None
        self.config_name = "server"

class LawClientConfig(ConfigReloader):
    """
    客户端配置类
    """
    def __init__(self):
        """Initializes a ClientConfig instance.
        """
        super().__init__()
        self.name = None
        self.version = None
        self.server_group = None
        self.env = None
        self.load_balance = None
        self.server_url = None
        self.config_name = "client"


class MethodCacheConfig:
    """
    方法缓存配置类
    """

    def __init__(self, cache_enable: bool, cache_num: int, cache_ttl: int, cache_memory_size: int):
        """Initializes a MethodCacheConfig instance.

        Args:
            cache_enable (bool): Whether caching is enabled.
            cache_num (int): The number of cache entries.
            cache_ttl (int): The time-to-live for cache entries in seconds.
            cache_memory_size (int): The maximum memory size for cache in bytes.
        """
        self.cache_enable = cache_enable
        self.cache_num = cache_num
        self.cache_ttl = cache_ttl
        self.cache_memory_size = cache_memory_size

    def hash_code(self):
        """
        计算缓存配置的哈希值。

        Returns:
            int: The hash value of the cache configuration.
        """
        return hash((self.cache_enable, self.cache_num, self.cache_ttl, self.cache_memory_size))

class MethodRetryConfig:
    """
    方法重试配置类
    """

    def __init__(self, retry_enable: bool, retry_num: int, retry_interval: int):
        """Initializes a MethodRetryConfig instance.

        Args:
            retry_enable (bool): Whether retry is enabled.
            retry_num (int): The number of retry attempts.
            retry_interval (int): The interval between retries in seconds.
        """
        self.retry_enable = retry_enable
        self.retry_num = retry_num
        self.retry_interval = retry_interval

    def hash_code(self):
        """
        计算重试配置的哈希值。

        Returns:
            int: The hash value of the retry configuration.
        """
        return hash((self.retry_enable, self.retry_num, self.retry_interval))

class MethodRateLimitConfig:
    """
    速率限制配置类。

    用于存储限流策略、存储方式、速率限制配额等核心参数。
    """

    # 定义所有允许的限流策略，用于有效性检查
    VALID_STRATEGIES = {"fixed_window", "sliding_window", "leaking_bucket", "token_bucket", "gcra"}
    VALID_STORAGES = {"memory", "redis"}

    def __init__(self, limits_enable: bool, limits_storge: str, limits_storge_url: str,
                 limits_strategies: str, limits_storge_amount: int, limits_storge_multiples: int,
                 limits_storge_options: Union[str, Dict[str, Any]]
                 ):
        """
        初始化一个 RateLimitConfig 实例。

        Args:
            limits_enable (bool): 是否启用速率限制。
            limits_storge (str): 限流存储方式，可选 "memory" (内存) 或 "redis"。
            limits_storge_url (str): 限流存储地址 (如 "127.0.0.1:6379")，仅当 limits_storge="redis" 时有效。
            limits_strategies (str): 限流策略，可选 "fixed_window", "sliding_window" 等。
            limits_storge_amount (int): 限制的配额/请求数。例如，每分钟允许 100 次请求，此值为 100。
            limits_storge_multiples (int): 时间窗口长度（秒）。例如，每 60 秒 (1 分钟) 的流量，此值为 60。
            limits_storge_options (str | dict): 存储相关的额外配置，如果是字符串则使用 ast.literal_eval 安全解析为字典。
        """
        self.limits_enable = limits_enable

        # 校验并设置存储方式
        if limits_storge not in self.VALID_STORAGES:
            raise ValueError(f"Invalid limits_storge: '{limits_storge}'. Must be one of {self.VALID_STORAGES}")
        self.limits_storge = limits_storge

        self.limits_storge_url = limits_storge_url

        # 校验并设置限流策略
        if limits_strategies not in self.VALID_STRATEGIES:
            raise ValueError(
                f"Invalid limits_strategies: '{limits_strategies}'. Must be one of {self.VALID_STRATEGIES}")
        self.limits_strategies = limits_strategies

        self.limits_storge_amount = limits_storge_amount
        self.limits_storge_multiples = limits_storge_multiples

        # 解析 limits_storge_options
        self.limits_storge_options = {}
        if isinstance(limits_storge_options, str):
            try:
                self.limits_storge_options = ast.literal_eval(limits_storge_options)
                if not isinstance(self.limits_storge_options, dict):
                    raise TypeError("Parsed limits_storge_options must be a dictionary.")
            except (ValueError, SyntaxError, TypeError) as e:
                raise ValueError(f"Error evaluating limits_storge_options string: {e}")
        elif isinstance(limits_storge_options, dict):
            self.limits_storge_options = limits_storge_options

    def hash_code(self):
        """
        计算限流配置的哈希值。

        Returns:
            int: The hash value of the rate limit configuration.
        """
        return hash((self.limits_enable, self.limits_storge, self.limits_storge_url,
                     self.limits_strategies, self.limits_storge_amount, self.limits_storge_multiples,
                     self.limits_storge_options))

class LawMethodConfig(ConfigReloader):
    """
    方法配置类
    """
    def __init__(self):
        """Initializes a MethodConfig instance.
        """
        super().__init__()
        self.method_name_map = {}
        self.config_name = "method"
        self.protobuf_type = "txt"

    def cache(self, method_name) -> MethodCacheConfig:
        cache_item = self._cache_config.get(method_name, {}).get("cache", {})
        return MethodCacheConfig(
            cache_enable=cache_item.get("cache_enable", False),
            cache_num=int(cache_item.get("cache_num", 10000)),
            cache_ttl=int(cache_item.get("cache_ttl", 3600)),
            cache_memory_size=int(cache_item.get("cache_memory_size", 104857600))
        )

    def retry(self, method_name) -> MethodRetryConfig:
        retry_item = self._cache_config.get(method_name, {}).get("retry", {})
        return MethodRetryConfig(
            retry_enable=retry_item.get("retry_enable", False),
            retry_num=int(retry_item.get("retry_num", 3)),
            retry_interval=int(retry_item.get("retry_interval", 1000))
        )


    def rate_limit(self, method_name) -> MethodRateLimitConfig:
        limits_item = self._cache_config.get(method_name, {}).get("limits", {})
        return MethodRateLimitConfig(
            limits_enable=limits_item.get("limits_enable", False),
            limits_storge=limits_item.get("limits_storge", "memory"),
            limits_storge_url = limits_item.get("limits_storge_url",  "127.0.0.1:6379"),
            limits_strategies = limits_item.get("limits_strategies", "fixed_window"),
            limits_storge_amount = limits_item.get("limits_storge_amount", 1),
            limits_storge_multiples = limits_item.get("limits_storge_multiples", 60),
            limits_storge_options = limits_item.get("limits_storge_options", {})
        )


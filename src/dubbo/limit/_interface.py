import abc
from abc import ABC
from datetime import timedelta
from typing import Dict

from throttled import Throttled, RateLimitResult, rate_limiter


class RateLimitKeyConfig:
    """
    RateLimitKeyConfig
    给每个key设置 不同的限流策略，如果没有，则默认为key
    """
    def __init__(self,limits_strategies: str="fixed_window", limits_storge_amount: int=2, limits_storge_multiples: int=10):
        """
        初始化一个 RateLimitKeyConfig 实例。
        注意，这个是针对某个用户或者某个使用方
        Args:
            limits_strategies (str): RateLimitKey的策略，可选 "fixed_window" (固定窗口) 或 "sliding_window" (滑动窗口) 或 "leaking_bucket" (漏桶) 或 "token_bucket" (令牌桶) 或 "gcra"
            limits_storge_amount (int): 速率限制存储的额度，如 redis 存储的额度
            limits_storge_multiples (int): 速率限制存储的倍数，如 redis 存储的倍数
        """
        self.limits_strategies = limits_strategies
        self.limits_storge_amount = limits_storge_amount
        self.limits_storge_multiples = limits_storge_multiples



class RataLimitFactory(ABC):
    """
    RataLimitFactory
    """
    def __init__(self, limit_config: Dict[str, RateLimitKeyConfig]):
        self.limit_config = limit_config
        self.limit_client = {"common": self.fixed_window(100, 10)}
        for key, value in self.limit_config.items():
            if value.limits_strategies == "fixed_window":
                self.limit_client[key] = self.fixed_window(value.limits_storge_amount, value.limits_storge_multiples)
            elif value.limits_strategies == "sliding_window":
                self.limit_client[key] = self.sliding_window(value.limits_storge_amount, value.limits_storge_multiples)
            elif value.limits_strategies == "token_bucket":
                self.limit_client[key] = self.token_bucket(value.limits_storge_amount, value.limits_storge_multiples)
            elif value.limits_strategies == "leaking_bucket":
                self.limit_client[key] = self.leaky_bucket(value.limits_storge_amount, value.limits_storge_multiples)
            elif value.limits_strategies == "gcra":
                self.limit_client[key] = self.gcra(value.limits_storge_amount, value.limits_storge_multiples)
            else:
                self.limit_client[key] = self.fixed_window(value.limits_storge_amount, value.limits_storge_multiples)

    @abc.abstractmethod
    def fixed_window(self, limits_storge_amount: int, limits_storge_multiples: int) -> Throttled:
        """
        fixed_window
        """
        pass

    @abc.abstractmethod
    def sliding_window(self, limits_storge_amount: int, limits_storge_multiples: int) -> Throttled:
        """
        sliding_window
        """
        pass

    @abc.abstractmethod
    def token_bucket(self, limits_storge_amount: int, limits_storge_multiples: int) -> Throttled:
        """
        token_bucket
        """
        pass


    @abc.abstractmethod
    def leaky_bucket(self, limits_storge_amount: int, limits_storge_multiples: int) -> Throttled:
        """
        leaky_bucket
        """
        pass

    @abc.abstractmethod
    def gcra(self, limits_storge_amount: int, limits_storge_multiples: int) -> Throttled:
        """
        gcra
        """
        pass

    def limit(self, key: str) -> RateLimitResult:
        throttled_client = self.limit_client.get(key)
        if not throttled_client:
            throttled_client = self.limit_client["common"]
        return throttled_client.limit(key=key)

    @staticmethod
    def quate(limits_storge_multiples, limits_storge_amount):
        quota = rate_limiter.per_duration(
            timedelta(seconds=limits_storge_multiples),
            limit=limits_storge_amount
        )
        return quota
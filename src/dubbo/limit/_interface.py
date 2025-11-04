import abc
from abc import ABC
from datetime import timedelta
from typing import Dict

from throttled import Throttled, RateLimitResult, rate_limiter, RateLimiterType

from dubbo.configcenter.lawgenes_config import RateLimitKeyConfig


class RataLimitFactory(ABC):
    """
    RataLimitFactory
    """
    def __init__(self, limit_config: Dict[str, RateLimitKeyConfig], server: str="", options: Dict=None):
        self.limit_config = limit_config
        self.server = server
        self.options = options
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

    def fixed_window(self, limits_storge_amount: int, limits_storge_multiples: int) -> Throttled:
        return Throttled(
            store=self.store(),
            using=RateLimiterType.FIXED_WINDOW.value,
            quota=self.quate(limits_storge_amount, limits_storge_multiples),
            )

    def sliding_window(self, limits_storge_amount: int, limits_storge_multiples: int) -> Throttled:
        return Throttled(
            store=self.store(),
            using=RateLimiterType.SLIDING_WINDOW.value,
            quota=self.quate(limits_storge_amount, limits_storge_multiples),
        )

    def token_bucket(self, limits_storge_amount: int, limits_storge_multiples: int) -> Throttled:
        return Throttled(
            store=self.store(),
            using=RateLimiterType.TOKEN_BUCKET.value,
            quota=self.quate(limits_storge_amount, limits_storge_multiples),
        )

    def gcra(self, limits_storge_amount: int, limits_storge_multiples: int) -> Throttled:
        return Throttled(
            store=self.store(),
            using=RateLimiterType.GCRA.value,
            quota=self.quate(limits_storge_amount, limits_storge_multiples),
        )

    def leaky_bucket(self, limits_storge_amount: int, limits_storge_multiples: int) -> Throttled:
        return Throttled(
            store=self.store(),
            using=RateLimiterType.LEAKING_BUCKET.value,
            quota=self.quate(limits_storge_amount, limits_storge_multiples),
        )


    def limit(self, key: str) -> RateLimitResult:
        throttled_client = self.limit_client.get(key)
        if not throttled_client:
            throttled_client = self.limit_client["common"]
        # 如果没有开启限流，则不限流
        if self.limit_config.get(key) and self.limit_config.get(key).limits_enable:
            pass
        else:
            return RateLimitResult(False, "")
        return throttled_client.limit(key=key)

    @staticmethod
    def quate(limits_storge_multiples, limits_storge_amount):
        quota = rate_limiter.per_duration(
            timedelta(seconds=limits_storge_multiples),
            limit=limits_storge_amount
        )
        return quota

    def store(self):
        pass
from throttled import Throttled, store, RateLimiterType

from ._interface import RataLimitFactory


class LocalLimit(RataLimitFactory):
    """
    LocalLimit
    """
    @staticmethod
    def store():
        return store.MemoryStore()

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

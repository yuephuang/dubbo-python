from throttled import store

from ._interface import RataLimitFactory


class RedisLimit(RataLimitFactory):
    """
    RedisLimit
    """
    def store(self):
        return store.RedisStore(
            server=self.server,
            options=self.options
        )
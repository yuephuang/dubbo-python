from throttled import store

from ._interface import RataLimitFactory


class LocalLimit(RataLimitFactory):
    """
    LocalLimit
    """

    def store(self):
        return store.MemoryStore()
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
import hashlib
import bisect
import random
from typing import Optional

from dubbo.cluster import LoadBalance
from dubbo.cluster.monitor.cpu import CpuMonitor
from dubbo.protocol import Invocation, Invoker


class AbstractLoadBalance(LoadBalance, abc.ABC):
    """
    The abstract load balance.
    """

    def select(self, invokers: list[Invoker], invocation: Invocation) -> Optional[Invoker]:
        if not invokers:
            return None

        if len(invokers) == 1:
            return invokers[0]

        return self.do_select(invokers, invocation)

    @abc.abstractmethod
    def do_select(self, invokers: list[Invoker], invocation: Invocation) -> Optional[Invoker]:
        """
        Do select an invoker from the list.
        :param invokers: The invokers.
        :type invokers: List[Invoker]
        :param invocation: The invocation.
        :type invocation: Invocation
        :return: The selected invoker. If no invoker is selected, return None.
        :rtype: Optional[Invoker]
        """
        raise NotImplementedError()


class RandomLoadBalance(AbstractLoadBalance):
    """
    Random load balance.
    """

    def do_select(self, invokers: list[Invoker], invocation: Invocation) -> Optional[Invoker]:
        randint = random.randint(0, len(invokers) - 1)
        return invokers[randint]


class CpuLoadBalance(AbstractLoadBalance):
    """
    CPU load balance.
    """

    def __init__(self):
        self._monitor: Optional[CpuMonitor] = None

    def set_monitor(self, monitor: CpuMonitor) -> None:
        """
        Set the CPU monitor.
        :param monitor: The CPU monitor.
        :type monitor: CpuMonitor
        """
        self._monitor = monitor

    def do_select(self, invokers: list[Invoker], invocation: Invocation) -> Optional[Invoker]:
        # get the CPU usage
        cpu_usages = self._monitor.get_cpu_usage(invokers)
        # Select the caller with the lowest CPU usage, 0 means CPU usage is unknown.
        available_invokers = []
        unknown_invokers = []

        for invoker, cpu_usage in cpu_usages.items():
            if cpu_usage == 0:
                unknown_invokers.append((cpu_usage, invoker))
            else:
                available_invokers.append((cpu_usage, invoker))

        if available_invokers:
            # sort and select the invoker with the lowest CPU usage
            available_invokers.sort(key=lambda x: x[0])
            return available_invokers[0][1]
        elif unknown_invokers:
            # get the invoker with unknown CPU usage randomly
            randint = random.randint(0, len(unknown_invokers) - 1)
            return unknown_invokers[randint][1]
        else:
            return None


class ConsistentHashLoadBalance(AbstractLoadBalance):
    """
    一致性哈希负载均衡器。
    在节点列表变更时才重建哈希环，避免每次请求都重复计算。
    """

    def __init__(self, virtual_nodes: int = 160):
        # 虚拟节点数，用于提高分布均匀性
        self.virtual_nodes = virtual_nodes
        # 存储哈希环的哈希值到Invoker的映射
        self._hash_ring: dict[int, Invoker] = {}
        # 缓存已排序的哈希值列表，用于二分查找
        self._sorted_hashes: list[int] = []
        # 缓存当前哈希环对应的Invoker列表，用于判断是否需要重建
        self._cached_invokers: set = set()

    @staticmethod
    def _get_hash(row_str: str) -> int:
        """
        计算字符串的哈希值。
        使用MD5哈希算法，返回一个32位的整数。
        """
        # 注意：此处移除了硬编码的 constant_hash_key，让哈希更依赖于输入。
        # 如果需要，可以将此作为参数传入。
        md5_str = hashlib.md5(row_str.encode("utf-8")).hexdigest()
        # 将16进制字符串转换为整数
        return int(md5_str, 16)

    def _rebuild_hash_ring(self, invokers: list[Invoker]):
        """
        重建哈希环。
        这个方法只在 invokers 列表发生变化时调用。
        """
        self._hash_ring.clear()

        num_invokers = len(invokers)
        if num_invokers == 0:
            self._sorted_hashes = []
            return

        # 确保每个节点至少有一个虚拟节点
        num_per_invoker = self.virtual_nodes // num_invokers
        remainder = self.virtual_nodes % num_invokers

        for i, invoker in enumerate(invokers):
            invoker_str = invoker.get_url().to_str()
            # 为每个真实节点创建虚拟节点
            # 增加虚拟节点数，以确保总数等于设定的 virtual_nodes
            virtual_nodes_count = num_per_invoker + (1 if i < remainder else 0)

            for j in range(virtual_nodes_count):
                virtual_key = f"{invoker_str}#{j}"
                hash_value = self._get_hash(virtual_key)
                self._hash_ring[hash_value] = invoker

        # 对所有虚拟节点的哈希值进行排序，只在重建时执行一次
        self._sorted_hashes = sorted(self._hash_ring.keys())
        self._cached_invokers = set(invoker.get_url().to_str() for invoker in invokers)
        print(f"哈希环已重建，包含 {len(self._sorted_hashes)} 个虚拟节点。")

    def check_invoker(self, invokers: list[Invoker]):
        """
        校验invoker 是否一致
        """
        return set(invoker.get_url().to_str() for invoker in invokers) == self._cached_invokers


    def do_select(self, invokers: list[Invoker], invocation: Invocation) -> Optional[Invoker]:
        """
        根据请求参数选择一个 Invoker。
        """
        if not invokers:
            return None

        if len(invokers) == 1:
            return invokers[0]

        # 检查 invokers 列表是否发生变化，如果变化则重建哈希环
        if not self.check_invoker(invokers):
            self._rebuild_hash_ring(invokers)

        if not self._sorted_hashes:
            return None

        # 根据调用参数生成 key，并计算哈希值
        key = str(invocation.get_argument()) if invocation.get_argument() else ""
        request_hash = self._get_hash(key)

        # 在排序好的哈希列表上使用二分查找
        # bisect_left 是 Python 标准库中进行二分查找的工具
        idx = bisect.bisect_left(self._sorted_hashes, request_hash)

        # 如果找不到，则返回环中的第一个节点（环形查找）
        if idx == len(self._sorted_hashes):
            idx = 0

        target_hash = self._sorted_hashes[idx]
        return self._hash_ring[target_hash]




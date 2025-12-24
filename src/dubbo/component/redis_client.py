
from typing import Optional, Union

import redis
import redis.asyncio as aioredis
from redis.asyncio.cluster import RedisCluster as AsyncRedisCluster
from redis.cluster import RedisCluster


class AsyncRedisClient:
    """
    支持单机模式和集群模式的 Redis 异步客户端封装。
    提供增强版 set 方法，支持 EX/PX/NX/XX 参数。
    """

    def __init__(
        self,
        nodes: Optional[Union[str, list]] = None,
        *,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: int = 5,
        decode_responses: bool = True,
        startup_nodes: Optional[list] = None,
        skip_full_coverage_check: bool = True,
    ):
        """
        初始化 Redis 异步客户端。
        如果提供了 nodes（字符串或列表），则按集群模式初始化；
        否则按单机模式初始化。

        :param nodes: 集群节点列表，如 ["host1:port1", "host2:port2"] 或单个字符串
        :param host: 单机模式主机
        :param port: 单机模式端口
        :param db: 单机模式数据库编号
        :param password: 密码
        :param socket_timeout: 套接字超时
        :param decode_responses: 是否自动解码响应
        :param startup_nodes: 兼容旧参数名
        :param skip_full_coverage_check: 集群模式下是否跳过全槽覆盖检查
        """
        # 优先使用 startup_nodes 兼容旧调用
        if startup_nodes is not None:
            nodes = startup_nodes

        if nodes:
            # 集群模式
            if isinstance(nodes, str):
                nodes = [nodes]
            cluster_nodes = [{"host": n.split(":")[0], "port": int(n.split(":")[1])} for n in nodes]
            self.r = AsyncRedisCluster(
                startup_nodes=cluster_nodes,
                password=password,
                socket_timeout=socket_timeout,
                decode_responses=decode_responses,
                skip_full_coverage_check=skip_full_coverage_check,
            )
            self.mode = "cluster"
        else:
            # 单机模式
            self.r = aioredis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                socket_timeout=socket_timeout,
                decode_responses=decode_responses,
            )
            self.mode = "standalone"

    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        增强版 SET 命令，支持 EX/PX/NX/XX 参数。

        :param key: 键
        :param value: 值
        :param ex: 过期时间（秒）
        :param px: 过期时间（毫秒）
        :param nx: 仅在键不存在时设置
        :param xx: 仅在键已存在时设置
        :return: 是否设置成功
        """
        return await self.r.set(key, value, ex=ex, px=px, nx=nx, xx=xx)

    async def get(self, key: str) -> Optional[str]:
        """
        获取键值。
        """
        return await self.r.get(key)

    async def delete(self, *keys: str) -> int:
        """
        删除一个或多个键。
        """
        return await self.r.delete(*keys)

    async def close(self):
        """
        关闭连接。
        """
        await self.r.close()

class RedisClient:
    """
    支持单机模式和集群模式的 Redis 客户端封装。
    提供增强版 set 方法，支持 EX/PX/NX/XX 参数。
    """

    def __init__(
        self,
        nodes: Optional[Union[str, list]] = None,
        *,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: int = 5,
        decode_responses: bool = True,
        startup_nodes: Optional[list] = None,
        skip_full_coverage_check: bool = True,
    ):
        """
        初始化 Redis 客户端。
        如果提供了 nodes（字符串或列表），则按集群模式初始化；
        否则按单机模式初始化。

        :param nodes: 集群节点列表，如 ["host1:port1", "host2:port2"] 或单个字符串
        :param host: 单机模式主机
        :param port: 单机模式端口
        :param db: 单机模式数据库编号
        :param password: 密码
        :param socket_timeout: 套接字超时
        :param decode_responses: 是否自动解码响应
        :param startup_nodes: 兼容旧参数名
        :param skip_full_coverage_check: 集群模式下是否跳过全槽覆盖检查
        """
        # 优先使用 startup_nodes 兼容旧调用
        if startup_nodes is not None:
            nodes = startup_nodes

        if nodes:
            # 集群模式
            if isinstance(nodes, str):
                nodes = [nodes]
            cluster_nodes = [{"host": n.split(":")[0], "port": int(n.split(":")[1])} for n in nodes]
            self.r = RedisCluster(
                startup_nodes=cluster_nodes,
                password=password,
                socket_timeout=socket_timeout,
                decode_responses=decode_responses,
                skip_full_coverage_check=skip_full_coverage_check,
            )
            self.mode = "cluster"
        else:
            # 单机模式
            self.r = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                socket_timeout=socket_timeout,
                decode_responses=decode_responses,
            )
            self.mode = "standalone"

    def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        增强版 SET 命令，支持 EX/PX/NX/XX 参数。

        :param key: 键
        :param value: 值
        :param ex: 过期时间（秒）
        :param px: 过期时间（毫秒）
        :param nx: 仅在键不存在时设置
        :param xx: 仅在键已存在时设置
        :return: 是否设置成功
        """
        return self.r.set(key, value, ex=ex, px=px, nx=nx, xx=xx)

    def get(self, key: str) -> Optional[str]:
        """
        获取键值。
        """
        return self.r.get(key)

    def delete(self, *keys: str) -> int:
        """
        删除一个或多个键。
        """
        return self.r.delete(*keys)

    def close(self):
        """
        关闭连接。
        """
        self.r.close()

# -*- coding: utf-8 -*-
"""
@Author:      huangyuepeng
@Project:     dubbo-demo
@File:        service.py
@Description: This file defines the Dubbo service for the lawgenesis application.
              It handles service registration, method exposure, and integrates caching.
@Create Date: 2025/6/30 17:03
"""

# --- 标准库导入 ---
import asyncio
import datetime
import os
import subprocess
import threading
import time
from contextlib import contextmanager
from functools import wraps
from typing import Union, Callable, Optional

# --- 第三方库导入 ---
import orjson
import requests
# --- 本地应用/库导入 ---
from dubbo import Dubbo, Server
from dubbo.cache.cache_client import CacheClient
from dubbo.configcenter.lawgenes_config import LawServerConfig, LawMethodConfig, NotifyConfig
from dubbo.configs import ServiceConfig, RegistryConfig
from dubbo.extension import extensionLoader
from dubbo.lawgenesis_proto import (
    ProtobufInterface,
    ResponseProto,
)
from dubbo.lawgenesis_proto import lawgenesis_pb2
from dubbo.lawgenesis_proto.metadata import LawMetaData, LawAuthInfo
from dubbo.lawgenesis_proto.rpc import rpc_server
from dubbo.limit.local_limit import LocalLimit
from dubbo.loggers import loggerFactory, TRACE_ID, CONTEXT_ID
from dubbo.monitor.prometheus import MetricsCollector
from dubbo.notify import NoticeFactory, ServerMetaData
from dubbo.protocol.triple.constants import GRpcCode
from dubbo.proxy.handlers import RpcServiceHandler

_LOGGER = loggerFactory.get_logger()

# --- 全局映射 ---
# 缓存客户端映射：{method_name: CacheClient}
cache_map: dict[str, CacheClient] = {}
# 限流器映射：{method_name: LocalLimit}
limit_map: dict[str, LocalLimit] = {}

metrics_controller = MetricsCollector(system_update_interval=2)


@contextmanager
def trace_context_manager(trace_id, context_id):
    """
    一个用于设置和清除 trace_id 的上下文管理器。
    """
    # 1. 记录旧的值 (Token)
    # ContextVar.set() 会返回一个用于恢复之前值的 Token
    token = TRACE_ID.set(trace_id)
    context = CONTEXT_ID.set(context_id)
    try:
        yield
    finally:
        # 3. 恢复到旧的值
        TRACE_ID.reset(token)
        CONTEXT_ID.reset(context)

class LawgenesisService:
    """
    表示一个 Dubbo 服务，可以暴露方法并处理请求。

    该服务封装了服务注册、方法处理、配置重载、
    通知、鉴权、限流和缓存等功能。
    """

    def __init__(self, law_server_config: LawServerConfig = LawServerConfig(),
                 method_config: LawMethodConfig = LawMethodConfig(),
                 notify_config: NotifyConfig = None,
                 ):
        """
        初始化 LawgenesisService。

        :param law_server_config: 服务器配置对象
        :param method_config: 方法配置对象
        :param notify_config: 通知配置对象
        """
        self.law_server_config = law_server_config
        self.law_method_config = method_config

        self._server_metadata: ServerMetaData = self.server_metadata()
        self.method_handlers = []
        self.subscribe_task = []
        self.notify_config = notify_config or NotifyConfig()

        # 启动一个后台线程来运行 asyncio 事件循环，用于配置订阅
        async_thread = threading.Thread(target=self._start_loop, daemon=True)
        async_thread.start()
        time.sleep(2)

        self.notify_factory: Optional[NoticeFactory] = extensionLoader.get_extension(NoticeFactory, "feishu")()
        self.notify_factory.server_name = self.law_server_config.name
        self.notify_factory.url = self.notify_config.url
        self.run = True

    @property
    def intranet_ip(self) -> str:
        """
        尝试获取服务器的内网 IP 地址。
        :return: IP 地址字符串，如果失败则返回错误信息。
        """
        try:
            interface = "eth0"
            command = f"ip route show dev {interface}"
            result = subprocess.run(
                command,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            output_lines = result.stdout.strip().split('\n')

            for line in output_lines:
                if 'default via' in line:
                    parts = line.split()
                    try:
                        gateway_ip = parts[2]
                        return gateway_ip
                    except IndexError:
                        return f"解析 '{interface}' 路由输出失败。"

            return f"在 '{interface}' 的路由表中未找到默认网关。"
        except Exception as e:
            return f"No intranet_ip found, {e}"

    @property
    def internet_ip(self) -> str:
        """
        尝试获取服务器的公网 IP 地址。
        :return: IP 地址字符串，如果失败则返回错误信息。
        """
        try:
            command = "curl ifconfig.me"
            result = subprocess.run(
                command,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return result.stdout.strip()

        except subprocess.CalledProcessError as e:
            return f"No Internet IP found. {e}"

    def server_metadata(self) -> ServerMetaData:
        """
        生成当前服务器的元数据。
        :return: ServerMetaData 对象
        """
        host_name = os.environ.get("HOSTNAME", "NOT HOSTNAME")

        return ServerMetaData(
            server_name=self.law_server_config.name,
            host=self.law_server_config.host,
            host_name=host_name,
            intranet_ip=self.intranet_ip,
            internet_ip=self.internet_ip,
            message="",
            start_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    @property
    def server(self) -> Union[Server, Dubbo]:
        """
        创建并返回一个 Dubbo 服务器实例。

        它根据是否提供了注册中心 URL 来决定是创建
        一个带注册中心的 Dubbo 实例还是一个独立的 Server 实例。
        :return: Server 或 Dubbo 实例
        """
        service_config = ServiceConfig(service_handler=self.service_handler(), host=self.law_server_config.host,
                                       port=self.law_server_config.port)
        if self.law_server_config.register_center_url:
            # 如果提供了注册中心，则使用 Dubbo 引导程序进行注册
            registry_config = RegistryConfig.from_url(self.law_server_config.register_center_url)
            registry_config.group = self.law_server_config.group
            registry_config.version = self.law_server_config.version
            bootstrap = Dubbo(registry_config=registry_config)
            return bootstrap.create_server(service_config)
        else:
            # 否则，创建一个独立的 Dubbo 服务器
            return Server(service_config)

    def service_handler(self) -> RpcServiceHandler:
        """
        为该服务创建并返回一个 RpcServiceHandler。
        这个 handler 包含了所有通过 @methods 装饰器注册的暴露方法。
        :return: RpcServiceHandler 实例
        """
        return RpcServiceHandler(
            service_name=self.law_server_config.name,
            method_handlers=self.method_handlers,
        )

    def methods(self, method_name, method_config: LawMethodConfig = None, protobuf_type="txt"):
        """
        一个装饰器工厂，用于注册、包装和暴露业务方法。

        它处理：
        - Protobuf 解析
        - 鉴权
        - 限流
        - 缓存 (获取与设置)
        - 统一的响应格式化
        - 异常处理和日志记录

        :param method_name: 暴露的方法名 (用于路由、缓存和限流)
        :param method_config: (可选) 该方法的特定配置
        :param protobuf_type: (可选) 期望的 Protobuf 类型 (默认为 "txt")
        :return: 装饰器
        """

        def decorator(func: Callable):
            """
            实际的装饰器，包装用户提供的业务函数。
            """

            @wraps(func)
            def wrapper(request: lawgenesis_pb2.LawgenesisRequest) -> lawgenesis_pb2.LawgenesisReply:
                """
                包装器函数，执行 RPC 调用的通用逻辑。
                :param request: 原始的 Protobuf 请求
                :return: 统一的 Protobuf 响应
                """
                st = time.perf_counter()
                protobuf_interface = extensionLoader.get_extension(ProtobufInterface, protobuf_type)
                law_basedata = LawMetaData(request.BADA)
                request_data = orjson.loads(request.DATA)
                serialize_func = protobuf_interface(request_data)
                with trace_context_manager(trace_id=law_basedata.trace_id, context_id=serialize_func.context_id):
                    _LOGGER.info(f"{method_name} start, start_time: {st}, trace_id: {law_basedata.trace_id}")

                    # 1. 检查数据类型
                    if law_basedata.data_type != protobuf_type:
                        err_msg = f"{method_name} data_type error, expect: {protobuf_type}, actual: {law_basedata.data_type}"
                        _LOGGER.error(err_msg)
                        response_data = ResponseProto(data={"message": err_msg}, context_id=serialize_func.context_id,
                                                      code=GRpcCode.INVALID_ARGUMENT.value).to_bytes()
                        return self.response(base_data=law_basedata.basedata, data=response_data, )

                    # 2. 鉴权
                    auth_info = LawAuthInfo(law_basedata.auth)
                    if not self.check_auth(auth_info):
                        _LOGGER.error(f"{method_name} auth error, trace_id: {law_basedata.trace_id}")
                        return self.response(
                            base_data=law_basedata.basedata,
                            data=ResponseProto(
                                data="auth error", context_id=serialize_func.context_id,
                                code=GRpcCode.UNAUTHENTICATED.value).to_bytes(),
                        )

                    # 3. 流控
                    limited_result = self.check_limit(method_name=method_name, key=auth_info.auth_id)
                    if not limited_result:
                        _LOGGER.error(f"{method_name} limited, trace_id: {law_basedata.trace_id}")
                        return self.response(
                            base_data=law_basedata.basedata, data=ResponseProto(
                                data="limited", context_id=serialize_func.context_id,
                                code=GRpcCode.RESOURCE_EXHAUSTED.value).to_bytes(),
                        )

                    # 4. 缓存获取
                    response_data = self.get_cache(method_name=method_name,
                                                   key=serialize_func.cache_key) if law_basedata.is_cache else None
                    if response_data:
                        _LOGGER.info(
                            f"{method_name} cache hit, key: {serialize_func.cache_key}, trace_id: {law_basedata.trace_id}")
                        return self.response(base_data=law_basedata.basedata, data=response_data)

                    _LOGGER.info(
                        f"{method_name} cache miss, key: {serialize_func.cache_key}, trace_id: {law_basedata.trace_id}")

                    # 5. 执行业务逻辑
                    try:
                        response = func(serialize_func, law_basedata)
                        if not isinstance(response, dict):
                            _LOGGER.error(
                                f"{method_name} response_data must be a dict, but got {type(response)}, trace_id: {law_basedata.trace_id}")
                            response_data = ResponseProto(data="response_data must be a dict",
                                                          context_id=serialize_func.context_id,
                                                          code=GRpcCode.INTERNAL.value).to_bytes()
                            return self.response(base_data=law_basedata.basedata, data=response_data)

                        # 6. 构造成功响应并设置缓存
                        response_data = ResponseProto(data=response, context_id=serialize_func.context_id,
                                                      code=GRpcCode.OK.value).to_bytes()
                        self.set_cache(method_name=method_name, key=serialize_func.cache_key, value=response_data)
                        return self.response(base_data=law_basedata.basedata, data=response_data)

                    except Exception as e:
                        # 7. 异常处理
                        # 关键优化：exc_info=True 会将完整的堆栈跟踪记录到日志中
                        _LOGGER.error(f"{method_name} error: {e}, trace_id: {law_basedata.trace_id}", exc_info=True)
                        response_data = ResponseProto(data=str(e), context_id=serialize_func.context_id,
                                                      code=GRpcCode.UNAVAILABLE.value).to_bytes()
                        return self.response(base_data=law_basedata.basedata, data=response_data)
                    finally:
                        et = time.perf_counter()
                        _LOGGER.info(
                            f"{method_name} end, end_time: {et}, cost: {(et - st)*1000:.4f}ms, trace_id: {law_basedata.trace_id}")

            # --- 装饰器工厂的执行部分 ---
            # 为一元方法创建 RpcMethodHandler，并添加到方法处理程序列表中
            _method_config = method_config or self.law_method_config
            self.method_handlers.append(rpc_server(method_name=method_name, func=wrapper))

            # 注册限流器
            limit_map[method_name] = LocalLimit(
                limit_config=_method_config.rate_limit(method_name=method_name).limits_keys_operation)

            # 注册缓存器
            cache_map[method_name] = CacheClient(_method_config.cache(method_name=method_name))
            metrics_controller.register_metrics(method_name=method_name)
            _LOGGER.info(f"Method '{method_name}' registered with caching and rate limiting.")
            return wrapper

        return decorator

    @staticmethod
    def response(base_data: lawgenesis_pb2.BaseData, data: bytes) -> lawgenesis_pb2.LawgenesisReply:
        """
        静态辅助方法，用于构造标准的 LawgenesisReply。
        :param base_data: 基础数据 (BADA)
        :param data: 序列化后的 ResponseProto (bytes)
        :return: LawgenesisReply 实例
        """
        return lawgenesis_pb2.LawgenesisReply(
            BADA=base_data,
            Response=data,
        )

    @staticmethod
    def get_cache(method_name, key):
        """
        从全局缓存映射中获取缓存。
        :param method_name: 方法名
        :param key: 缓存键
        :return: 缓存的数据 (bytes) 或 None
        """
        cache_client = cache_map.get(method_name)
        return cache_client.get(key)

    @staticmethod
    def set_cache(method_name, key, value):
        """
        将数据设置到全局缓存映射中。
        :param method_name: 方法名
        :param key: 缓存键
        :param value: 缓存值 (bytes)
        :return: 缓存设置结果
        """
        cache_client = cache_map.get(method_name)
        return cache_client.set(key, value)

    @staticmethod
    def check_auth(auth_info: LawAuthInfo) -> bool:
        """
        执行基本的鉴权检查。
        :param auth_info: 包含鉴权信息的对象
        :return: True (通过) 或 False (失败)
        """
        # TODO: 硬编码的 auth_key "lawgenesis" 应该移到安全配置中。
        if auth_info.auth_key != "lawgenesis":
            _LOGGER.warning(f"Authentication failed for auth_id: {auth_info.auth_id}")
            return False
        return True

    @staticmethod
    def check_limit(method_name, key) -> bool:
        """
        检查指定方法的key是否受到限流。
        :param method_name: 方法名
        :param key: 限流键 (通常是 auth_id)
        :return: True (未限流) 或 False (已限流)
        """
        limited_client = limit_map.get(method_name)
        # 修正拼写错误：limite_result -> limit_result
        limit_result = limited_client.limit(key=key)
        if limit_result.limited:
            _LOGGER.error(f"{method_name} limited for key: {key}, state: {limit_result._state_values}")
            return False
        return True

    async def subscribe(self):
        """
        异步任务，用于启动和监控配置的重载。
        """
        _LOGGER.info("Starting configuration subscribers...")
        await self.law_server_config.async_start_reloader()
        await self.law_method_config.async_start_reloader()
        await self.notify_config.async_start_reloader()
        _LOGGER.info("Configuration subscribers started.")
        while True:
            # 保持任务活动
            await asyncio.sleep(1)

    def _start_loop(self):
        """在新线程中运行 asyncio 事件循环的函数"""
        # 1. 创建并设置新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 2. 在新循环中创建并启动订阅任务
        loop.create_task(self.subscribe())

        # 3. 启动循环，这将阻塞此线程直到循环停止
        _LOGGER.info("异步后台线程已启动事件循环。")
        try:
            loop.run_forever()
        finally:
            loop.close()
            _LOGGER.info("异步后台线程事件循环已停止。")

    async def async_start(self):
        """
        启动服务：启动 Dubbo 服务，发送启动通知，并维持主循环。
        """
        _LOGGER.info(f"Starting Dubbo server: {self.law_server_config.name}...")
        # 假设 self.server.start() 是非阻塞的，或在其自己的线程中运行
        self.server.start()
        _LOGGER.info(f"Dubbo server '{self.law_server_config.name}' started.")

        # 发送启动通知
        await self.notify_factory.async_send_table(
            title="🟢服务启动", subtitle=self.law_server_config.name, elements=[self.server_metadata()]
        )

        try:
            while self.run:
                metrics_data = metrics_controller.get_all_metrics()
                if self.law_server_config.pushgateway_url:
                    try:
                        url =  f"{self.law_server_config.pushgateway_url}/metrics/job/{self.server_metadata().server_name}/instance/{self.server_metadata().host_name}"
                        resp = requests.post(url, data=metrics_data)
                        resp.raise_for_status()
                    except Exception as e:
                        _LOGGER.error(f"推送到 Pushgateway 失败: {e}")
                        continue
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            _LOGGER.info("服务器关闭信号已接收...")
            self.run = False  # 触发循环退出
        finally:
            # 在循环退出时（无论是正常停止还是异常），发送停止通知
            _LOGGER.info("服务器正在停止，发送停止通知...")
            await self.notify_factory.async_send_table(
                title="🔴服务停止", subtitle=self.law_server_config.name, elements=[self.server_metadata()]
            )
            _LOGGER.info("服务已停止。")

    def start(self):
        """
        服务的同步启动入口点。

        它使用 asyncio.run() 来运行 `async_start` 协程，
        这将阻塞主线程直到 `async_start` 完成。
        """
        try:
            asyncio.run(self.async_start())
        except KeyboardInterrupt:
            _LOGGER.info("主线程捕获到 KeyboardInterrupt，程序退出。")

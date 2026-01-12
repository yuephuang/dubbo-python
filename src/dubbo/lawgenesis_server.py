# -*- coding: utf-8 -*-
"""
@Author:      huangyuepeng
@Project:     dubbo-demo
@File:        lawgenesis_server.py
@Description: This file defines the Dubbo service for the lawgenesis application.
              It handles service registration, method exposure, caching, rate limiting,
              authentication, monitoring, and configuration management.
@Create Date: 2025/6/30 17:03
"""

# --- 标准库导入 ---
import asyncio
import datetime
import os
import threading
import time
from contextlib import contextmanager
from functools import wraps
from typing import Union, Callable, Optional, Any

# --- 第三方库导入 ---
import orjson
from prometheus_client import start_http_server

# --- 本地应用/库导入 ---
from dubbo import Dubbo, Server
from dubbo.cache.cache_client import CacheClient
from dubbo.component.asynchronous import AsyncRpcCallable
from dubbo.component.nacos_client import NacosClinet
from dubbo.configcenter.lawgenes_config import LawServerConfig, LawMethodConfig, NotifyConfig, LAW_SERVER_CONFIG, \
    METHOD_CONFIG, NOTIFY_CONFIG
from dubbo.configs import ServiceConfig
from dubbo.constants import common_constants
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
from dubbo.monitor.prometheus import EnhancedMetricsCollector
from dubbo.notify import NoticeFactory, ServerMetaData
from dubbo.protocol.triple.constants import GRpcCode
from dubbo.proxy.handlers import RpcServiceHandler, RpcMethodHandler
from dubbo.url import create_url

# --- 全局常量和配置 ---
_LOGGER = loggerFactory.get_logger()

try:
    async_rpc_callable = AsyncRpcCallable() if common_constants.ASYNC_RPC_ENABLED else None
except Exception as e:
    _LOGGER.error(f"初始化 AsyncRpcCallable 失败: {e}")
    async_rpc_callable = None


# --- 上下文管理器 ---
@contextmanager
def trace_context_manager(trace_id, context_id):
    """
    用于设置和清除 trace_id 的上下文管理器，确保调用链路追踪的正确性。
    """
    token = TRACE_ID.set(trace_id)
    context = CONTEXT_ID.set(context_id)
    try:
        yield
    finally:
        TRACE_ID.reset(token)
        CONTEXT_ID.reset(context)


class LawgenesisService:
    """
    Lawgenesis Dubbo服务实现类，提供完整的服务注册、方法暴露、
    缓存、限流、鉴权、监控和配置管理功能。
    """

    def __init__(self,
                 law_server_config: LawServerConfig = LAW_SERVER_CONFIG,
                 method_config: LawMethodConfig = METHOD_CONFIG,
                 notify_config: Optional[NotifyConfig] = NOTIFY_CONFIG,
                 ):
        self.law_server_config = law_server_config
        self.law_method_config = method_config
        self.notify_config = notify_config or NotifyConfig()
        self.nacos_register_client = NacosClinet()
        self.run = True
        self.method_handlers: list[RpcMethodHandler] = []
        self._cache_map: dict[str, CacheClient] = {}
        self._limit_map: dict[str, LocalLimit] = {}
        self._server_metadata: ServerMetaData = self._get_server_metadata()
        self._start_config_subscription()
        self._init_notification_service()
        self.metrics_collector = EnhancedMetricsCollector(law_server_config.name,
                                                          service_version=law_server_config.version)
        _LOGGER.info(f"LawgenesisService initialized for service: {self.law_server_config.name}")

    @property
    def _intranet_ip(self) -> str:
        return self.law_server_config.host

    @property
    def _internet_ip(self) -> str:
        return ""

    def _get_server_metadata(self, message: str = "") -> ServerMetaData:
        host_name = os.environ.get("HOSTNAME", "NOT HOSTNAME")
        return ServerMetaData(
            server_name=self.law_server_config.name,
            host=self.law_server_config.host,
            host_name=host_name,
            intranet_ip=self._intranet_ip,
            internet_ip=self._internet_ip,
            message=f"接口: {self.law_server_config.port}, {message}",
            start_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _start_config_subscription(self) -> None:
        config_thread = threading.Thread(target=self._run_config_loop, daemon=True)
        config_thread.start()

    def _init_notification_service(self) -> None:
        self._notify_factory: Optional[NoticeFactory] = extensionLoader.get_extension(NoticeFactory, "feishu")()
        self._notify_factory.server_name = self.law_server_config.name
        self._notify_factory.url = self.notify_config.url

    def _get_service_handler(self) -> RpcServiceHandler:
        return RpcServiceHandler(service_name=str(self.law_server_config.name), method_handlers=self.method_handlers)

    @property
    def _server(self) -> Union[Server, Dubbo]:
        service_config = ServiceConfig(service_handler=self._get_service_handler(), host="0.0.0.0",
                                       port=self.law_server_config.port)
        return Server(service_config)

    def methods(self, method_name: str,
                method_config: Optional[LawMethodConfig] = None,
                protobuf_type: str = "txt",
                async_type: bool = False):
        """
        方法注册装饰器工厂，支持同步和异步业务函数。
        """
        if method_name == "healthy":
            raise ValueError(f"{method_name} is a reserved method name")
        method_config = method_config or self.law_method_config

        def decorator(func: Callable):
            # 判断原函数是否为异步函数
            is_async_func = asyncio.iscoroutinefunction(func)

            @wraps(func)
            def wrapper(request: lawgenesis_pb2.LawgenesisRequest) -> lawgenesis_pb2.LawgenesisReply:
                """
                内部包装器逻辑，处理通用的 RPC 生命周期。
                注：为了兼容性，如果内部 func 是异步的，此 wrapper 在 Dubbo 框架下可能需要
                配合具体的异步 RPC 处理器，或者在内部通过事件循环运行。
                这里提供一个通用的逻辑处理模板。
                """
                start_time = time.perf_counter()
                protobuf_interface = extensionLoader.get_extension(ProtobufInterface, protobuf_type)
                law_metadata = LawMetaData(request.BADA)
                request_data = orjson.loads(request.DATA)
                serialize_func = protobuf_interface(request_data)
                with self.metrics_collector.start_request_timer(method_name=method_name):
                    with trace_context_manager(trace_id=law_metadata.trace_id, context_id=serialize_func.context_id):
                        _LOGGER.info(f"[{method_name}] Request start, trace_id: {law_metadata.trace_id}")

                        # 1. 校验逻辑
                        if law_metadata.data_type != protobuf_type:
                            self.metrics_collector.record_request(method_name=method_name, grpc_status_code=GRpcCode.INVALID_ARGUMENT.value)
                            return self._create_response(law_metadata.basedata,
                                                         ResponseProto(data={"message": "Type mismatch"},
                                                                       context_id=serialize_func.context_id,
                                                                       code=GRpcCode.INVALID_ARGUMENT.value).to_bytes())

                        if not self._check_auth(LawAuthInfo(law_metadata.auth)):
                            self.metrics_collector.record_request(method_name=method_name, grpc_status_code=GRpcCode.UNAUTHENTICATED.value)
                            return self._create_response(law_metadata.basedata, ResponseProto(data="Auth failed",
                                                                                              context_id=serialize_func.context_id,
                                                                                              code=GRpcCode.UNAUTHENTICATED.value).to_bytes())

                        if not self._check_rate_limit(method_name, LawAuthInfo(law_metadata.auth).auth_id):
                            self.metrics_collector.record_request(method_name=method_name, grpc_status_code=GRpcCode.RESOURCE_EXHAUSTED.value)
                            return self._create_response(law_metadata.basedata, ResponseProto(data="Rate limited",
                                                                                              context_id=serialize_func.context_id,
                                                                                              code=GRpcCode.RESOURCE_EXHAUSTED.value).to_bytes())

                        # 2. 异步任务发布 (消息队列模式)
                        if async_type:
                            try:
                                request_data["callback_url"] = law_metadata.callback_url
                                task_id = async_rpc_callable.pushlish_task(method_name, request_data)
                                return self._create_response(law_metadata.basedata, ResponseProto(data={"task_id": task_id},
                                                                                                  context_id=serialize_func.context_id,
                                                                                                  code=GRpcCode.OK.value).to_bytes())
                            except Exception as e:
                                _LOGGER.error(f"Async task publish failed: {e}")

                        # 3. 缓存检查
                        if law_metadata.is_cache:
                            cached = self._get_cache(method_name, serialize_func.cache_key)
                            if cached: return self._create_response(law_metadata.basedata, cached)

                        # 4. 执行业务逻辑 (区分同步异步)
                        try:
                            if is_async_func:
                                # 如果是异步函数，需要在当前/全局事件循环中运行
                                # 注意：在同步 wrapper 中调用异步 func 需要 run_until_complete 或类似机制
                                try:
                                    loop = asyncio.get_event_loop()
                                except RuntimeError:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)

                                if loop.is_running():
                                    # 如果循环正在运行（例如已经在 async 环境下），则需要特殊处理
                                    # 这里假设 dubbo 框架调用 wrapper 是同步的
                                    future = asyncio.run_coroutine_threadsafe(func(serialize_func), loop)
                                    response = future.result()
                                else:
                                    response = loop.run_until_complete(func(serialize_func))
                            else:
                                response = func(serialize_func)

                            # 5. 构造响应
                            if not isinstance(response, dict):
                                raise ValueError("Response must be dict")

                            response_data = ResponseProto(data=response, context_id=serialize_func.context_id,
                                                          code=GRpcCode.OK.value).to_bytes()
                            if law_metadata.is_cache:
                                self._set_cache(method_name, serialize_func.cache_key, response_data)

                            return self._create_response(law_metadata.basedata, response_data)

                        except Exception as e:
                            _LOGGER.error(f"[{method_name}] Error: {e}", exc_info=True)
                            return self._create_response(law_metadata.basedata,
                                                         ResponseProto(data=str(e), context_id=serialize_func.context_id,
                                                                       code=GRpcCode.UNAVAILABLE.value).to_bytes())
                        finally:
                            cost = (time.perf_counter() - start_time) * 1000
                            _LOGGER.info(f"[{method_name}] End, cost: {cost:.4f}ms")

            # 注册逻辑
            self.method_handlers.append(rpc_server(method_name=method_name, func=wrapper))
            self._limit_map[method_name] = LocalLimit(
                limit_config=method_config.rate_limit(method_name=method_name).limits_keys_operation)
            self._cache_map[method_name] = CacheClient(method_config.cache(method_name=method_name))
            self._metrics_collector.register_metrics(method_name=method_name)

            # 异步执行器注册，这里需要确保 async_rpc_callable 能处理协程
            if async_rpc_callable:
                async_rpc_callable.register_method(method_name=method_name, thread_num=1, method_instance=func)

            _LOGGER.info(f"Method '{method_name}' registered (Async: {is_async_func})")
            return wrapper

        return decorator

    def custom_method(self):
        @self.methods("health")
        def health_check(request: Any, law_basedata: LawMetaData = None) -> dict:
            return {"status": "ok"}

    @staticmethod
    def _create_response(base_data: lawgenesis_pb2.BaseData, data: bytes) -> lawgenesis_pb2.LawgenesisReply:
        return lawgenesis_pb2.LawgenesisReply(BADA=base_data, Response=data)

    def _get_cache(self, method_name: str, key: str) -> Optional[bytes]:
        cache_client = self._cache_map.get(method_name)
        return cache_client.get(key) if cache_client else None

    def _set_cache(self, method_name: str, key: str, value: bytes) -> bool:
        cache_client = self._cache_map.get(method_name)
        return cache_client.set(key, value) if cache_client else False

    @staticmethod
    def _check_auth(auth_info: LawAuthInfo) -> bool:
        return auth_info.auth_key == "lawgenesis"

    def _check_rate_limit(self, method_name: str, key: str) -> bool:
        limit_client = self._limit_map.get(method_name)
        if not limit_client: return True
        return not limit_client.limit(key=key).limited

    async def _subscribe_config(self):
        _LOGGER.info("Starting configuration subscribers...")
        await self.law_server_config.async_start_reloader()
        await self.law_method_config.async_start_reloader()
        await self.notify_config.async_start_reloader()
        while self.run: await asyncio.sleep(1)

    def _run_config_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(self._subscribe_config())
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def async_start(self):
        _LOGGER.info(f"Starting Dubbo server: {self.law_server_config.name}...")
        self.custom_method()
        self._server.start()
        await self._notify_factory.async_send_table(title="🟢服务启动", subtitle=self.law_server_config.name,
                                                    elements=[self._get_server_metadata()])

        if async_rpc_callable:
            async_rpc_callable.start_consumer()
        try:
            self.nacos_register_client.register_service(
                url=create_url(f"tri://{self.law_server_config.host}:{self.law_server_config.port}"))
        except Exception as e:
            _LOGGER.error(f"Failed to register service: {e}")
        # metrics 启动
        start_http_server(8000)
        try:
            while self.run:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            self.run = False
        finally:
            await self.async_stop()

    async def async_stop(self):
        _LOGGER.info(f"Stopping Dubbo server: {self.law_server_config.name}...")
        self.nacos_register_client.unregister_service(
            url=create_url(f"tri://{self.law_server_config.host}:{self.law_server_config.port}"))
        self.run = False
        await self._notify_factory.async_send_table(title="🔴服务开始停止", subtitle=self.law_server_config.name,
                                                    elements=[self._get_server_metadata()])
        await asyncio.sleep(300)
        await self._notify_factory.async_send_table(title="🔴服务彻底停止", subtitle=self.law_server_config.name,
                                                    elements=[self._get_server_metadata()])

    def start(self):
        try:
            asyncio.run(self.async_start())
        except KeyboardInterrupt:
            _LOGGER.info("Exiting.")

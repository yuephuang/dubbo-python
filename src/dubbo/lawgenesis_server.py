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
import subprocess
import threading
import time
from contextlib import contextmanager
from functools import wraps
from typing import Union, Callable, Optional, Any

# --- 第三方库导入 ---
import orjson
import requests

# --- 本地应用/库导入 ---
from dubbo import Dubbo, Server
from dubbo.cache.cache_client import CacheClient
from dubbo.component.asynchronous import AsyncRpcCallable
from dubbo.component.nacos_client import NacosClinet
from dubbo.configcenter.lawgenes_config import LawServerConfig, LawMethodConfig, NotifyConfig, LAW_SERVER_CONFIG, \
    METHOD_CONFIG, NOTIFY_CONFIG
from dubbo.configs import ServiceConfig
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
from dubbo.proxy.handlers import RpcServiceHandler, RpcMethodHandler
from dubbo.url import create_url

# --- 全局常量和配置 ---
_LOGGER = loggerFactory.get_logger()



try:
    async_rpc_callable = AsyncRpcCallable()
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
        """
        初始化LawgenesisService实例。

        :param law_server_config: 服务器配置对象
        :param method_config: 方法配置对象
        :param notify_config: 通知配置对象
        """
        # --- 配置初始化 ---
        self.law_server_config = law_server_config
        self.law_method_config = method_config
        self.notify_config = notify_config or NotifyConfig()
        self.nacos_register_client = NacosClinet()
        # --- 状态管理 ---
        self.run = True

        # --- 组件管理 ---
        self.method_handlers: list[RpcMethodHandler] = []  # 方法处理器列表
        self._cache_map: dict[str, CacheClient] = {}  # 缓存客户端映射
        self._limit_map: dict[str, LocalLimit] = {}  # 限流器映射
        self._metrics_collector = MetricsCollector(system_update_interval=2)  # 指标收集器

        # --- 服务元数据 ---
        self._server_metadata: ServerMetaData = self._get_server_metadata()

        # --- 配置订阅 ---
        self._start_config_subscription()

        # --- 通知服务 ---
        self._init_notification_service()

        _LOGGER.info(f"LawgenesisService initialized for service: {self.law_server_config.name}")

    # --- 网络相关方法 ---
    @property
    def _intranet_ip(self) -> str:
        """
        获取服务器内网IP地址。

        :return: 内网IP地址字符串，获取失败时返回错误信息
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

            for line in result.stdout.strip().split('\n'):
                if 'default via' in line:
                    parts = line.split()
                    try:
                        return parts[2]  # 返回网关IP作为内网IP
                    except IndexError:
                        return f"解析 '{interface}' 路由输出失败"

            return f"在 '{interface}' 的路由表中未找到默认网关"
        except Exception as e:
            return f"未找到内网IP: {e}"

    @property
    def _internet_ip(self) -> str:
        """
        获取服务器公网IP地址。

        :return: 公网IP地址字符串，获取失败时返回错误信息
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
            return f"未找到公网IP: {e}"

    def _get_server_metadata(self) -> ServerMetaData:
        """
        生成当前服务器的元数据信息。

        :return: ServerMetaData对象，包含服务器的完整元数据
        """
        host_name = os.environ.get("HOSTNAME", "NOT HOSTNAME")

        return ServerMetaData(
            server_name=self.law_server_config.name,
            host=self.law_server_config.host,
            host_name=host_name,
            intranet_ip=self._intranet_ip,
            internet_ip=self._internet_ip,
            message="",
            start_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _start_config_subscription(self) -> None:
        """
        启动配置订阅服务，监控配置变更。
        """
        # 启动后台线程运行配置订阅事件循环
        config_thread = threading.Thread(target=self._run_config_loop, daemon=True)
        config_thread.start()
        time.sleep(2)  # 等待线程初始化完成

    def _init_notification_service(self) -> None:
        """
        初始化通知服务组件。
        """
        self._notify_factory: Optional[NoticeFactory] = extensionLoader.get_extension(NoticeFactory, "feishu")()
        self._notify_factory.server_name = self.law_server_config.name
        self._notify_factory.url = self.notify_config.url

    # --- 服务相关方法 ---
    def _get_service_handler(self) -> RpcServiceHandler:
        """
        创建RPC服务处理器实例。

        :return: RpcServiceHandler实例，包含所有注册的方法处理器
        """
        return RpcServiceHandler(
            service_name=str(self.law_server_config.name),
            method_handlers=self.method_handlers,
        )

    @property
    def _server(self) -> Union[Server, Dubbo]:
        """
        创建并返回Dubbo服务器实例。

        根据是否提供注册中心URL，决定创建带注册中心的Dubbo实例
        还是独立的Server实例。

        :return: Server或Dubbo实例
        """
        service_config = ServiceConfig(
            service_handler=self._get_service_handler(),
            host=self.law_server_config.host,
            port=self.law_server_config.port
        )
        return Server(service_config)

    # --- 方法装饰器 ---
    def methods(self, method_name: str,
                method_config: Optional[LawMethodConfig] = None,
                protobuf_type: str = "txt",
                async_type: bool = True):
        """
        方法注册装饰器工厂，用于包装和暴露业务方法。

        自动处理：
        - Protobuf数据解析与序列化
        - 请求鉴权验证
        - 流量限制控制
        - 缓存管理（获取与设置）
        - 统一响应格式化
        - 异常处理与日志记录
        - 性能指标收集

        :param method_name: 暴露的方法名（用于路由、缓存和限流）
        :param method_config: 该方法的特定配置（可选）
        :param protobuf_type: 期望的Protobuf类型（默认为"txt"）
        :return: 装饰器函数
        """
        if method_config in ["healthy"]:
            raise ValueError(f"{method_name} is a reserved method name")
        method_config = method_config or self.law_method_config
        def decorator(func: Callable):
            """
            实际的装饰器，包装用户提供的业务函数。
            """

            @wraps(func)
            def wrapper(request: lawgenesis_pb2.LawgenesisRequest) -> lawgenesis_pb2.LawgenesisReply:
                """
                方法包装器，执行RPC调用的完整生命周期管理。

                :param request: 原始Protobuf请求
                :return: 统一格式的Protobuf响应
                """
                # --- 请求处理开始 ---
                start_time = time.perf_counter()

                # 1. 请求解析
                protobuf_interface = extensionLoader.get_extension(ProtobufInterface, protobuf_type)
                law_metadata = LawMetaData(request.BADA)
                request_data = orjson.loads(request.DATA)
                serialize_func = protobuf_interface(request_data)

                with trace_context_manager(trace_id=law_metadata.trace_id, context_id=serialize_func.context_id):
                    _LOGGER.info(f"[{method_name}] Request start, trace_id: {law_metadata.trace_id}")

                    # 2. 数据类型检查
                    if law_metadata.data_type != protobuf_type:
                        err_msg = f"[{method_name}] Data type mismatch, expect: {protobuf_type}, actual: {law_metadata.data_type}"
                        _LOGGER.error(err_msg)
                        response_data = ResponseProto(
                            data={"message": err_msg},
                            context_id=serialize_func.context_id,
                            code=GRpcCode.INVALID_ARGUMENT.value
                        ).to_bytes()
                        return self._create_response(base_data=law_metadata.basedata, data=response_data)

                    # 3. 权限验证
                    auth_info = LawAuthInfo(law_metadata.auth)
                    if not self._check_auth(auth_info):
                        _LOGGER.error(f"[{method_name}] Authentication failed, trace_id: {law_metadata.trace_id}")
                        return self._create_response(
                            base_data=law_metadata.basedata,
                            data=ResponseProto(
                                data="Authentication failed",
                                context_id=serialize_func.context_id,
                                code=GRpcCode.UNAUTHENTICATED.value
                            ).to_bytes(),
                        )

                    # 4. 流量限制检查
                    if not self._check_rate_limit(method_name, auth_info.auth_id):
                        _LOGGER.error(f"[{method_name}] Rate limited, trace_id: {law_metadata.trace_id}")
                        return self._create_response(
                            base_data=law_metadata.basedata,
                            data=ResponseProto(
                                data="Rate limited",
                                context_id=serialize_func.context_id,
                                code=GRpcCode.RESOURCE_EXHAUSTED.value
                            ).to_bytes(),
                        )

                    if async_type:
                        # 异步调用
                        try:
                            request_data["callback_url"] = law_metadata.callback_url
                            task_id = async_rpc_callable.pushlish_task(method_name, request_data)
                            _LOGGER.info(f"[{method_name}] Async task published, task_id: {task_id}, trace_id: {law_metadata.trace_id}")
                            return self._create_response(
                                base_data=law_metadata.basedata,
                                data=ResponseProto(
                                    data={"task_id": task_id},
                                    context_id=serialize_func.context_id,
                                    code=GRpcCode.OK.value
                                ).to_bytes()
                            )
                        except Exception as e:
                            _LOGGER.error(f"[{method_name}] Async task failed, trace_id: {law_metadata.trace_id}, e: {e}", exc_info=True)

                    # 5. 缓存获取
                    if law_metadata.is_cache:
                        cached_data = self._get_cache(method_name, serialize_func.cache_key)
                        if cached_data:
                            _LOGGER.info(f"[{method_name}] Cache hit, key: {serialize_func.cache_key}, trace_id: {law_metadata.trace_id}")
                            return self._create_response(base_data=law_metadata.basedata, data=cached_data)

                        _LOGGER.info(f"[{method_name}] Cache miss, key: {serialize_func.cache_key}, trace_id: {law_metadata.trace_id}")

                    # 6. 执行业务逻辑
                    try:
                        response = func(serialize_func)

                        # 7. 响应格式检查
                        if not isinstance(response, dict):
                            _LOGGER.error(f"[{method_name}] Response must be dict, got {type(response)}, trace_id: {law_metadata.trace_id}")
                            response_data = ResponseProto(
                                data="Invalid response format",
                                context_id=serialize_func.context_id,
                                code=GRpcCode.INTERNAL.value
                            ).to_bytes()
                            return self._create_response(base_data=law_metadata.basedata, data=response_data)

                        # 8. 构造成功响应
                        response_data = ResponseProto(
                            data=response,
                            context_id=serialize_func.context_id,
                            code=GRpcCode.OK.value
                        ).to_bytes()

                        # 9. 设置缓存
                        if law_metadata.is_cache:
                            self._set_cache(method_name, serialize_func.cache_key, response_data)

                        return self._create_response(base_data=law_metadata.basedata, data=response_data)

                    except Exception as e:
                        # 10. 异常处理
                        _LOGGER.error(f"[{method_name}] Execution error: {e}, trace_id: {law_metadata.trace_id}", exc_info=True)
                        response_data = ResponseProto(
                            data=str(e),
                            context_id=serialize_func.context_id,
                            code=GRpcCode.UNAVAILABLE.value
                        ).to_bytes()
                        return self._create_response(base_data=law_metadata.basedata, data=response_data)
                    finally:
                        # 11. 请求处理结束
                        end_time = time.perf_counter()
                        cost_time = (end_time - start_time) * 1000
                        _LOGGER.info(f"[{method_name}] Request end, cost: {cost_time:.4f}ms, trace_id: {law_metadata.trace_id}")

            # 1. 注册方法处理器
            self.method_handlers.append(rpc_server(method_name=method_name, func=wrapper))

            # 2. 注册限流器
            self._limit_map[method_name] = LocalLimit(
                limit_config=method_config.rate_limit(method_name=method_name).limits_keys_operation
            )

            # 3. 注册缓存客户端
            self._cache_map[method_name] = CacheClient(method_config.cache(method_name=method_name))

            # 4. 注册指标收集
            self._metrics_collector.register_metrics(method_name=method_name)

            # 5, 注册异步执行器
            async_rpc_callable.register_method(method_name=method_name, thread_num=1, method_instance=func)

            _LOGGER.info(f"Method '{method_name}' registered with caching and rate limiting.")
            return wrapper


        return decorator

    def custom_method(self):
        """
        自定义方法，用于处理特殊业务逻辑。
        """
        @self.methods("health")
        def health_check(request: Any, law_basedata: LawMetaData=None) -> bool:
            """
            健康检查方法，用于验证服务是否正常运行。

            :param request: LawgenesisRequest实例
            :return: LawgenesisReply实例
            """
            return True


    # --- 辅助方法 ---
    @staticmethod
    def _create_response(base_data: lawgenesis_pb2.BaseData, data: bytes) -> lawgenesis_pb2.LawgenesisReply:
        """
        构造标准的LawgenesisReply响应。

        :param base_data: 基础数据(BADA)
        :param data: 序列化后的ResponseProto数据
        :return: LawgenesisReply实例
        """
        return lawgenesis_pb2.LawgenesisReply(
            BADA=base_data,
            Response=data,
        )

    def _get_cache(self, method_name: str, key: str) -> Optional[bytes]:
        """
        从缓存中获取数据。

        :param method_name: 方法名
        :param key: 缓存键
        :return: 缓存的数据(bytes)或None
        """
        cache_client = self._cache_map.get(method_name)
        if cache_client:
            return cache_client.get(key)
        return None

    def _set_cache(self, method_name: str, key: str, value: bytes) -> bool:
        """
        将数据设置到缓存中。

        :param method_name: 方法名
        :param key: 缓存键
        :param value: 缓存值(bytes)
        :return: 缓存设置结果
        """
        cache_client = self._cache_map.get(method_name)
        if cache_client:
            return cache_client.set(key, value)
        return False

    @staticmethod
    def _check_auth(auth_info: LawAuthInfo) -> bool:
        """
        执行请求鉴权检查。

        :param auth_info: 包含鉴权信息的对象
        :return: True表示鉴权通过，False表示鉴权失败
        """
        # TODO: 硬编码的auth_key应该移到安全配置中
        if auth_info.auth_key != "lawgenesis":
            _LOGGER.warning(f"Authentication failed for auth_id: {auth_info.auth_id}")
            return False
        return True

    def _check_rate_limit(self, method_name: str, key: str) -> bool:
        """
        检查请求是否触发流量限制。

        :param method_name: 方法名
        :param key: 限流键(通常是auth_id)
        :return: True表示未限流，False表示已限流
        """
        limit_client = self._limit_map.get(method_name)
        if not limit_client:
            return True  # 没有限流器时默认允许请求

        limit_result = limit_client.limit(key=key)
        if limit_result.limited:
            _LOGGER.error(f"[{method_name}] Rate limited for key: {key}, state: {limit_result._state_values}")
            return False
        return True

    # --- 配置订阅方法 ---
    async def _subscribe_config(self):
        """
        异步配置订阅任务，监控配置变更并自动重载。
        """
        _LOGGER.info("Starting configuration subscribers...")

        # 启动所有配置的重载器
        await self.law_server_config.async_start_reloader()
        await self.law_method_config.async_start_reloader()
        await self.notify_config.async_start_reloader()
        _LOGGER.info("Configuration subscribers started successfully.")

        # 保持任务运行
        while self.run:
            await asyncio.sleep(1)

    def _run_config_loop(self):
        """
        在独立线程中运行配置订阅的事件循环。
        """
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 启动配置订阅任务
        loop.create_task(self._subscribe_config())

        _LOGGER.info("Configuration subscription loop started.")
        try:
            loop.run_forever()
        finally:
            loop.close()
            _LOGGER.info("Configuration subscription loop stopped.")

    # --- 服务启动方法 ---
    async def async_start(self):
        """
        异步启动服务，执行完整的服务启动流程。

        包括：
        - 启动Dubbo服务器
        - 发送服务启动通知
        - 定期推送监控指标
        - 处理服务关闭信号
        """
        _LOGGER.info(f"Starting Dubbo server: {self.law_server_config.name}...")
        # 加载自定义方法
        self.custom_method()
        # 启动Dubbo服务器
        self._server.start()
        _LOGGER.info(f"Dubbo server '{self.law_server_config.name}' started successfully.")
        # 发送启动通知
        await self._notify_factory.async_send_table(
            title="🟢服务启动",
            subtitle=self.law_server_config.name,
            elements=[self._get_server_metadata()]
        )
        async_rpc_callable.start_consumer()
        try:
            self.nacos_register_client.register_service(url=create_url(f"tri://{self.law_server_config.host}:{self.law_server_config.port}"))
        except Exception as e:
            _LOGGER.error(f"Failed to register service: {e}")
        try:
            # 主循环：定期推送指标
            while self.run:
                metrics_data = self._metrics_collector.get_all_metrics()

                # 推送到Prometheus Pushgateway
                if self.law_server_config.pushgateway_url:
                    try:
                        server_meta = self._get_server_metadata()
                        url = f"{self.law_server_config.pushgateway_url}/metrics/job/{server_meta.server_name}/instance/{server_meta.host_name}"
                        resp = requests.post(url, data=metrics_data)
                        resp.raise_for_status()
                    except Exception as e:
                        _LOGGER.error(f"Failed to push metrics to Pushgateway: {e}")
                        continue

                await asyncio.sleep(1)

        except (KeyboardInterrupt, asyncio.CancelledError):
            _LOGGER.info("Server shutdown signal received...")
            self.run = False  # 触发循环退出
        finally:
            # 发送停止通知
            _LOGGER.info("Server stopping, sending shutdown notification...")
            await self._notify_factory.async_send_table(
                title="🔴服务停止",
                subtitle=self.law_server_config.name,
                elements=[self._get_server_metadata()]
            )
            _LOGGER.info("Server stopped successfully.")
            await self.async_stop()

    async def async_stop(self):
        """
        异步停止服务，执行完整的服务停止流程。

        包括：
        - 关闭Dubbo服务器
        - 发送服务停止通知
        - 清理资源
        """
        _LOGGER.info(f"Stopping Dubbo server: {self.law_server_config.name}...")
        self.nacos_register_client.unregister_service(url=create_url(f"tri://{self.law_server_config.host}:{self.law_server_config.port}"))
        # 停止需要等待一会，10s后自动停止
        await asyncio.sleep(300)
        # 关闭Dubbo服务器
        self.run = False
        _LOGGER.info(f"Dubbo server '{self.law_server_config.name}' stopped successfully.")

        # 发送停止通知
        await self._notify_factory.async_send_table(
            title="🔴服务停止",
            subtitle=self.law_server_config.name,
            elements=[self._get_server_metadata()]
        )
        _LOGGER.info("Server stopped successfully.")

    def start(self):
        """
        服务的同步启动入口点。

        使用asyncio.run()运行async_start协程，
        阻塞主线程直到服务停止。
        """
        try:
            asyncio.run(self.async_start())
        except KeyboardInterrupt:
            _LOGGER.info("KeyboardInterrupt received in main thread, exiting.")
        except Exception as e:
            _LOGGER.error(f"Error in main thread: {e}")
        finally:
            self._server.stop()
            _LOGGER.info("Exiting main thread.")

    def stop(self):
        """
        服务的同步停止入口点。

        使用asyncio.run()运行async_stop协程，
        阻塞主线程直到服务停止。
        """
        self.stop()
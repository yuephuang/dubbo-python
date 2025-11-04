# -*- coding: utf-8 -*-
"""
@Author:      huangyuepeng
@Project:     dubbo-demo
@File:        service.py
@Description: This file defines the Dubbo service for the lawgenesis application.
              It handles service registration, method exposure, and integrates caching.
@Create Date: 2025/6/30 17:03
"""
import asyncio
import datetime
import os
import subprocess
import threading
import time
from functools import wraps
from typing import Union, Callable, Optional

import orjson

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
from dubbo.loggers import loggerFactory
from dubbo.notify import NoticeFactory, ServerMetaData
from dubbo.protocol.triple.constants import GRpcCode
from dubbo.proxy.handlers import RpcServiceHandler

_LOGGER = loggerFactory.get_logger()
cache_map: dict[str, CacheClient] = {}
limit_map: dict[str, LocalLimit] = {}
# 映射不同类型的数据到对应的 Protobuf 类
class LawgenesisService:
    """
    表示一个 Dubbo 服务，可以暴露方法并处理请求。
    """

    def __init__(self, law_server_config: LawServerConfig = LawServerConfig(),
                 method_config: LawMethodConfig = LawMethodConfig(),
                 notify_config: NotifyConfig = None,
                 ):
        self.law_server_config = law_server_config
        self.law_method_config = method_config

        self._server_metadata: ServerMetaData = self.server_metadata()
        self.method_handlers = []
        self.subscribe_task = []
        self.notify_config = notify_config or NotifyConfig()
        async_thread = threading.Thread(target=self._start_loop, daemon=True)
        async_thread.start()
        self.notify_factory: Optional[NoticeFactory] = extensionLoader.get_extension(NoticeFactory, "feishu")()
        self.notify_factory.server_name = self.law_server_config.name
        self.notify_factory.url = self.notify_config.url
        self.run = True
        time.sleep(1)

    @property
    def intranet_ip(self):
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
                # 寻找包含 'default via' 的行
                if 'default via' in line:
                    parts = line.split()
                    try:
                        # 'default' [0], 'via' [1], '192.168.1.1' [2]
                        gateway_ip = parts[2]
                        return gateway_ip
                    except IndexError:
                        return f"解析 '{interface}' 路由输出失败。"

            return f"在 '{interface}' 的路由表中未找到默认网关。"

        except subprocess.CalledProcessError as e:
            return f"No intranet_ip  found, {e} "
        except Exception as e:
            return f"No intranet_ip  found, {e}"

    @property
    def internet_ip(self):
        try:
            # 获取公网 IP
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
        return ServerMetaData(
            server_name=self.law_server_config.name,
            host=self.law_server_config.host,
            host_name=os.environ.get("HOSTNAM", "NOT HOSTNAME"),
            intranet_ip=self.intranet_ip,
            internet_ip=self.internet_ip,
            message="",
            start_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    @property
    def server(self) -> Union[Server, Dubbo]:
        """
        创建并返回一个 Dubbo 服务器实例。
        它根据是否提供了注册中心 URL 来配置服务器。
        """
        service_config = ServiceConfig(service_handler=self.service_handler(), host=self.law_server_config.host,
                                       port=self.law_server_config.port)
        if self.law_server_config.register_center_url:
            # 如果提供了注册中心，则使用 Dubbo 引导程序进行注册

            registry_config = RegistryConfig.from_url(self.law_server_config.register_center_url)
            registry_config.group = self.law_server_config._group
            registry_config.version = self.law_server_config.version
            bootstrap = Dubbo(registry_config=registry_config)
            return bootstrap.create_server(service_config)
        else:
            # 否则，创建一个独立的 Dubbo 服务器
            return Server(service_config)

    def service_handler(self) -> RpcServiceHandler:
        """
        为该服务创建并返回一个 RpcServiceHandler。
        这个 handler 包含了所有暴露的方法。
        """
        return RpcServiceHandler(
            service_name=self.law_server_config.name,
            method_handlers=self.method_handlers,
        )

    def methods(self, method_name, method_config: LawMethodConfig = None, protobuf_type="txt"):
        def decorator(func: Callable):
            """
            为指定的方法添加装饰器。
            """
            @wraps(func)
            def wrapper(request: lawgenesis_pb2.LawgenesisRequest) -> lawgenesis_pb2.LawgenesisReply:
                st = time.perf_counter()
                protobuf_interface = extensionLoader.get_extension(ProtobufInterface, protobuf_type)
                law_basedata = LawMetaData(request.BADA)
                request_data = orjson.loads(request.DATA)
                serialize_func = protobuf_interface(request_data)
                _LOGGER.info(f"{method_name} start, start_time: {st}, trace_id: {law_basedata.trace_id}")
                if law_basedata.data_type != protobuf_type:
                    err_msg = f"{method_name} data_type error, expect: {protobuf_type}, actual: {law_basedata.data_type}"
                    _LOGGER.error(err_msg)
                    response_data = ResponseProto(data={"message": err_msg}, context_id=serialize_func.context_id,
                                                  code=GRpcCode.INVALID_ARGUMENT.value).to_bytes()
                    return self.response(base_data=law_basedata.basedata, data=response_data,)
                # 鉴权
                auth_info = LawAuthInfo(law_basedata.auth)
                if not self.check_auth(auth_info):
                    _LOGGER.error(f"{method_name} auth error")
                    return self.response(
                        base_data=law_basedata.basedata,
                        data=ResponseProto(
                            data="auth error", context_id=serialize_func.context_id, code=GRpcCode.UNAUTHENTICATED.value).to_bytes(),
                    )
                # 流控
                limited_result = self.check_limit(method_name=method_name, key=auth_info.auth_id)
                if not limited_result:
                    _LOGGER.error(f"{method_name} limited")
                    return self.response(
                        base_data=law_basedata.basedata, data=ResponseProto(
                            data="limited", context_id=serialize_func.context_id, code=GRpcCode.RESOURCE_EXHAUSTED.value).to_bytes(),
                    )

                # 缓存
                response_data = self.get_cache(method_name=method_name, key=serialize_func.cache_key) if law_basedata.is_cache else None
                if response_data:
                    _LOGGER.info(f"{method_name} cache hit, key: {serialize_func.cache_key}")
                    return self.response(base_data=law_basedata.basedata, data=response_data)

                try:
                    response = func(serialize_func, law_basedata)
                    if not isinstance(response, dict):
                        _LOGGER.error(f"{method_name} response_data must be a dict")
                        response_data = ResponseProto(data="response_data must be a dict",
                                                       context_id=serialize_func.context_id,
                                                       code=GRpcCode.INTERNAL.value).to_bytes()
                        return self.response(base_data=law_basedata.basedata, data=response_data)

                    response_data = ResponseProto(data=response, context_id=serialize_func.context_id,
                                                  code=GRpcCode.OK.value).to_bytes()
                    self.set_cache(method_name=method_name, key=serialize_func.cache_key, value=response_data)
                    return self.response(base_data=law_basedata.basedata, data=response_data)

                except Exception as e:
                    response_data = ResponseProto(data=str(e), context_id=serialize_func.context_id,
                                                  code=GRpcCode.UNAVAILABLE.value).to_bytes()
                    _LOGGER.error(f"{method_name} error: {e}")
                    return self.response(base_data=law_basedata.basedata, data=response_data)
                finally:
                    et = time.perf_counter()
                    _LOGGER.info(f"{method_name} end, end_time: {et}, cost: {et - st}, trace_id: {law_basedata.trace_id}")

            # 为一元方法创建 RpcMethodHandler，并添加到方法处理程序列表中
            _method_config = method_config or self.law_method_config
            self.method_handlers.append(rpc_server(method_name=method_name, func=wrapper))
            # 注册缓存器
            limit_map[method_name] = LocalLimit(
                limit_config=_method_config.rate_limit(method_name=method_name).limits_keys_operation)
            cache_map[method_name] = CacheClient(_method_config.cache(method_name=method_name))
            return wrapper

        return decorator

    @staticmethod
    def response(base_data: lawgenesis_pb2.BaseData, data: bytes) -> lawgenesis_pb2.LawgenesisReply:
        return lawgenesis_pb2.LawgenesisReply(
            BADA=base_data,
            Response=data,
        )


    @staticmethod
    def get_cache(method_name, key):
        cache_client = cache_map.get(method_name)
        return cache_client.get(key)

    @staticmethod
    def set_cache(method_name, key, value):
        cache_client = cache_map.get(method_name)
        return cache_client.set(key, value)

    @staticmethod
    def check_auth(auth_info: LawAuthInfo) -> bool:
        if auth_info.auth_key != "lawgenesis":
            return False
        return True
    @staticmethod
    def check_limit(method_name,  key) -> bool:
        limited_client = limit_map.get(method_name)
        limite_result = limited_client.limit(key=key)
        if limite_result.limited:
            _LOGGER.error(f"{method_name} limited, {limite_result._state_values}")
            return False
        return True

    async def subscribe(self):
        """"""
        await self.law_server_config.async_start_reloader()
        await self.law_method_config.async_start_reloader()
        await self.notify_config.async_start_reloader()
        while True:
            await asyncio.sleep(1)

    def _start_loop(self):
        """在新线程中运行事件循环的函数"""
        # 1. 创建并设置新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 2. 在新循环中创建并启动任务
        loop.create_task(self.subscribe())
        # 3. 启动循环，这将阻塞此线程直到循环停止
        _LOGGER.info("异步后台线程已启动事件循环。")
        loop.run_forever()

    async def async_start(self):
        """启动服务：在后台启动异步任务，然后启动主同步服务"""
        # 1. 创建并启动线程来运行异步循环

        self.server.start()
        await self.notify_factory.send_table(
            title="🟢服务启动", subtitle=self.law_server_config.name, elements=[self.server_metadata()]
        )
        while self.run:
            await asyncio.sleep(1)

        await self.notify_factory.send_table(
            title="🔴服务停止", subtitle=self.law_server_config.name, elements=[self.server_metadata()]
        )

    def start(self):
        """启动服务"""
        asyncio.run(self.async_start())
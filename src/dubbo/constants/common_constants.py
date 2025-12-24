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

"""
Common constants for dubbo-python framework.

This module contains common constant definitions used across the dubbo-python framework,
including framework core constants, service configuration, network settings, and more.
All constants support environment variable overrides for flexible configuration.
"""

import os

# --- 核心框架常量 --- 
DUBBO_VALUE = os.environ.get("DUBBO_VALUE", "dubbo")  # Dubbo框架标识

# --- 服务引用与导出 --- 
REFER_KEY = os.environ.get("REFER_KEY", "refer")  # 服务引用键名
EXPORT_KEY = os.environ.get("EXPORT_KEY", "export")  # 服务导出键名

# --- 协议相关 --- 
PROTOCOL_KEY = os.environ.get("PROTOCOL_KEY", "protocol")  # 协议键名
TRIPLE = os.environ.get("TRIPLE", "triple")  # Triple协议全称
TRIPLE_SHORT = os.environ.get("TRIPLE_SHORT", "tri")  # Triple协议简称

# --- 服务端/客户端标识 --- 
SIDE_KEY = os.environ.get("SIDE_KEY", "side")  # 角色（服务端/客户端）键名
SERVER_VALUE = os.environ.get("SERVER_VALUE", "server")  # 服务端标识值
CLIENT_VALUE = os.environ.get("CLIENT_VALUE", "client")  # 客户端标识值

# --- 方法与服务 --- 
METHOD_KEY = os.environ.get("METHOD_KEY", "method")  # 方法键名
SERVICE_KEY = os.environ.get("SERVICE_KEY", "service")  # 服务键名
SERVICE_HANDLER_KEY = os.environ.get("SERVICE_HANDLER_KEY", "service-handler")  # 服务处理器键名

# --- 服务分组 --- 
GROUP_KEY = os.environ.get("GROUP_KEY", "group")  # 分组键名

# --- 网络与端口设置 --- 
LOCAL_HOST_KEY = os.environ.get("LOCAL_HOST_KEY", "localhost")  # 本地主机键名
LOCAL_HOST_VALUE = os.environ.get("LOCAL_HOST_VALUE", "0.0.0.0")  # 本地主机默认值
DEFAULT_SERVER_PORT = int(os.environ.get("DEFAULT_PORT", 50001))  # 默认服务器端口
DEFAULT_SERVER_NAME = os.environ.get("DEFAULT_SERVER_NAME", "lawgenesis")  # 默认服务器名称
DEFAULT_SERVER_VERSION = os.environ.get("DEFAULT_SERVER_VERSION", "1.0.0")  # 默认服务器版本

# --- 环境配置 --- 
ENV_KEY = os.environ.get("ENV_KEY", "dev")  # 环境标识（开发、测试、生产等）

# --- Nacos注册中心配置 --- 
NACOS_HOST = os.environ.get("NACOS_HOST", "")  # Nacos服务器主机
NACOS_PORT = os.environ.get("NACOS_PORT", "")  # Nacos服务器端口
NACOS_NAMESPACE = os.environ.get("NACOS_NAMESPACE", "")  # Nacos命名空间
NACOS_USERNAME = os.environ.get("NACOS_USERNAME", "")  # Nacos用户名
NACOS_PASSWORD = os.environ.get("NACOS_PASSWORD", "")  # Nacos密码
NACOS_URL = os.environ.get("NACOS_URL", f"nacos://{NACOS_USERNAME}:{NACOS_PASSWORD}@{NACOS_HOST}:{NACOS_PORT}?namespace={NACOS_NAMESPACE}")  # Nacos完整URL

# redis 配置
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")  # Redis服务器主机
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))  # Redis服务器端口
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "123456")  # Redis密码
REDIS_DB = int(os.environ.get("REDIS_DB", 0))  # Redis数据库索引


# --- Prometheus监控配置 --- 
PUSHGATEWAY_URL = os.environ.get("PUSHGATEWAY_URL", "")  # Prometheus Pushgateway URL

# --- SSL配置 --- 
SSL_ENABLED_KEY = os.environ.get("SSL_ENABLED_KEY", "ssl-enabled")  # SSL启用键名

# --- 序列化配置 --- 
SERIALIZATION_KEY = os.environ.get("SERIALIZATION_KEY", "serialization")  # 序列化键名
SERIALIZER_KEY = os.environ.get("SERIALIZER_KEY", "serializer")  # 序列化器键名
DESERIALIZER_KEY = os.environ.get("DESERIALIZER_KEY", "deserializer")  # 反序列化器键名

# --- 压缩配置 --- 
COMPRESSION_KEY = os.environ.get("COMPRESSION_KEY", "compression")  # 压缩键名
COMPRESSOR_KEY = os.environ.get("COMPRESSOR_KEY", "compressor")  # 压缩器键名
DECOMPRESSOR_KEY = os.environ.get("DECOMPRESSOR_KEY", "decompressor")  # 解压缩器键名

# --- 传输层配置 --- 
TRANSPORTER_KEY = os.environ.get("TRANSPORTER_KEY", "transporter")  # 传输器键名
TRANSPORTER_DEFAULT_VALUE = os.environ.get("TRANSPORTER_DEFAULT_VALUE", "aio")  # 默认传输器（asyncio）

# --- 布尔值表示 --- 
TRUE_VALUE = os.environ.get("TRUE_VALUE", "true")  # 布尔值true的字符串表示
FALSE_VALUE = os.environ.get("FALSE_VALUE", "false")  # 布尔值false的字符串表示

# --- RPC类型 --- 
RPC_TYPE_KEY = os.environ.get("RPC_TYPE_KEY", "rpc-type")  # RPC类型键名

# --- 方法描述符 --- 
METHOD_DESCRIPTOR_KEY = os.environ.get("METHOD_DESCRIPTOR_KEY", "method-descriptor")  # 方法描述符键名

# --- 负载均衡 --- 
LOADBALANCE_KEY = os.environ.get("LOADBALANCE_KEY", "loadbalance")  # 负载均衡键名

# --- 分隔符定义 --- 
PATH_SEPARATOR = os.environ.get("PATH_SEPARATOR", "/")  # 路径分隔符
PROTOCOL_SEPARATOR = os.environ.get("PROTOCOL_SEPARATOR", "://")  # 协议分隔符
ANY_VALUE = os.environ.get("ANY_VALUE", "*")  # 通配符值
COMMA_SEPARATOR = os.environ.get("COMMA_SEPARATOR", ",")  # 逗号分隔符
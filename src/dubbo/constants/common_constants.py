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

import os

DUBBO_VALUE = os.environ.get("DUBBO_VALUE", "dubbo")

REFER_KEY = os.environ.get("REFER_KEY", "refer")
EXPORT_KEY = os.environ.get("EXPORT_KEY", "export")

PROTOCOL_KEY = os.environ.get("PROTOCOL_KEY", "protocol")
TRIPLE = os.environ.get("TRIPLE", "triple")
TRIPLE_SHORT = os.environ.get("TRIPLE_SHORT", "tri")

SIDE_KEY = os.environ.get("SIDE_KEY", "side")
SERVER_VALUE = os.environ.get("SERVER_VALUE", "server")
CLIENT_VALUE = os.environ.get("CLIENT_VALUE", "client")

METHOD_KEY = os.environ.get("METHOD_KEY", "method")
SERVICE_KEY = os.environ.get("SERVICE_KEY", "service")

SERVICE_HANDLER_KEY = os.environ.get("SERVICE_HANDLER_KEY", "service-handler")

GROUP_KEY = os.environ.get("GROUP_KEY", "group")

LOCAL_HOST_KEY = os.environ.get("LOCAL_HOST_KEY", "localhost")
LOCAL_HOST_VALUE = os.environ.get("LOCAL_HOST_VALUE", "0.0.0.0")
DEFAULT_SERVER_PORT = int(os.environ.get("DEFAULT_PORT", 50001))
DEFAULT_SERVER_NAME = os.environ.get("DEFAULT_SERVER_NAME", "lawgenesis")
DEFAULT_SERVER_VERSION = os.environ.get("DEFAULT_SERVER_VERSION", "1.0.0")

ENV_KEY = os.environ.get("ENV_KEY", "dev")


NACOS_HOST = os.environ.get("NACOS_HOST", "")
NACOS_PORT = os.environ.get("NACOS_PORT", "")
NACOS_NAMESPACE = os.environ.get("NACOS_NAMESPACE", "")
NACOS_USERNAME = os.environ.get("NACOS_USERNAME", "")
NACOS_PASSWORD = os.environ.get("NACOS_PASSWORD", "")
NACOS_URL = os.environ.get("NACOS_URL", f"nacos://{NACOS_USERNAME}:{NACOS_PASSWORD}@{NACOS_HOST}:{NACOS_PORT}?namespace={NACOS_NAMESPACE}")

PUSHGATEWAY_URL = os.environ.get("PUSHGATEWAY_URL", "")

SSL_ENABLED_KEY = os.environ.get("SSL_ENABLED_KEY", "ssl-enabled")

SERIALIZATION_KEY = os.environ.get("SERIALIZATION_KEY", "serialization")
SERIALIZER_KEY = os.environ.get("SERIALIZER_KEY", "serializer")
DESERIALIZER_KEY = os.environ.get("DESERIALIZER_KEY", "deserializer")


COMPRESSION_KEY = os.environ.get("COMPRESSION_KEY", "compression")
COMPRESSOR_KEY = os.environ.get("COMPRESSOR_KEY", "compressor")
DECOMPRESSOR_KEY = os.environ.get("DECOMPRESSOR_KEY", "decompressor")


TRANSPORTER_KEY = os.environ.get("TRANSPORTER_KEY", "transporter")
TRANSPORTER_DEFAULT_VALUE = os.environ.get("TRANSPORTER_DEFAULT_VALUE", "aio")

TRUE_VALUE = os.environ.get("TRUE_VALUE", "true")
FALSE_VALUE = os.environ.get("FALSE_VALUE", "false")

RPC_TYPE_KEY = os.environ.get("RPC_TYPE_KEY", "rpc-type")

METHOD_DESCRIPTOR_KEY = os.environ.get("METHOD_DESCRIPTOR_KEY", "method-descriptor")

LOADBALANCE_KEY = os.environ.get("LOADBALANCE_KEY", "loadbalance")

PATH_SEPARATOR = os.environ.get("PATH_SEPARATOR", "/")
PROTOCOL_SEPARATOR = os.environ.get("PROTOCOL_SEPARATOR", "://")
ANY_VALUE = os.environ.get("ANY_VALUE", "*")
COMMA_SEPARATOR = os.environ.get("COMMA_SEPARATOR", ",")
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
Configuration constants for dubbo-python framework.

This module contains constant definitions related to configuration management,
including environment settings, versioning, grouping, and transport configuration.
All constants support environment variable overrides for flexible deployment.
"""

import os

# --- 环境配置 --- 
ENVIRONMENT = os.environ.get("ENVIRONMENT", "environment")  # 环境键名
TEST_ENVIRONMENT = os.environ.get("TEST_ENVIRONMENT", "test")  # 测试环境标识
DEVELOPMENT_ENVIRONMENT = os.environ.get("DEVELOPMENT_ENVIRONMENT", "develop")  # 开发环境标识
PRODUCTION_ENVIRONMENT = os.environ.get("PRODUCTION_ENVIRONMENT", "product")  # 生产环境标识

# --- 版本与分组 --- 
VERSION = os.environ.get("VERSION", "version")  # 版本键名
GROUP = os.environ.get("GROUP", "group")  # 分组键名

# --- 传输层配置 --- 
TRANSPORT = os.environ.get("TRANSPORT", "transport")  # 传输层键名
AIO_TRANSPORT = os.environ.get("AIO_TRANSPORT", "aio")  # 异步IO传输层标识
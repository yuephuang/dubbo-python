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
Logger constants for dubbo-python framework.

This module contains constant definitions related to logging configuration,
including log levels, console logging, file logging, and Loki integration.
It also defines the FileRotateType enum for file rotation strategies.
All constants support environment variable overrides for flexible logging configuration.
"""

import enum
import os

__all__ = [
    "FileRotateType",
    "LEVEL_KEY",
    "CONSOLE_ENABLED_KEY",
    "FILE_ENABLED_KEY",
    "FILE_DIR_KEY",
    "FILE_NAME_KEY",
    "FILE_ROTATE_KEY",
    "FILE_MAX_BYTES_KEY",
    "FILE_INTERVAL_KEY",
    "FILE_BACKUP_COUNT_KEY",
    "DEFAULT_LEVEL_VALUE",
    "DEFAULT_CONSOLE_ENABLED_VALUE",
    "DEFAULT_FILE_ENABLED_VALUE",
    "DEFAULT_FILE_DIR_VALUE",
    "DEFAULT_FILE_NAME_VALUE",
    "DEFAULT_FILE_MAX_BYTES_VALUE",
    "DEFAULT_FILE_INTERVAL_VALUE",
    "DEFAULT_FILE_BACKUP_COUNT_VALUE",
]


@enum.unique
class FileRotateType(enum.Enum):
    """
    The file rotating type enum.

    :cvar NONE: No rotating - single log file without rotation.
    :cvar SIZE: Rotate the file by size - creates new file when maximum size is reached.
    :cvar TIME: Rotate the file by time - creates new file at specified time intervals.
    """

    NONE = "NONE"  # 不进行日志文件轮换
    SIZE = "SIZE"  # 按文件大小进行轮换
    TIME = "TIME"  # 按时间间隔进行轮换


# --- 日志配置键名 --- 
# 全局日志配置
LEVEL_KEY = "logger.level"  # 日志级别配置键名

# 控制台日志配置
CONSOLE_ENABLED_KEY = "logger.console.enable"  # 控制台日志启用键名

# 文件日志配置
FILE_ENABLED_KEY = "logger.file.enable"  # 文件日志启用键名
FILE_DIR_KEY = "logger.file.dir"  # 日志文件目录键名
FILE_NAME_KEY = "logger.file.name"  # 日志文件名键名
FILE_ROTATE_KEY = "logger.file.rotate"  # 日志文件轮换策略键名
FILE_MAX_BYTES_KEY = "logger.file.maxbytes"  # 单日志文件最大字节数键名（按大小轮换时使用）
FILE_INTERVAL_KEY = "logger.file.interval"  # 日志轮换时间间隔键名（按时间轮换时使用）
FILE_BACKUP_COUNT_KEY = "logger.file.backupcount"  # 日志文件备份数量键名

# --- 日志默认值 --- 
# 全局默认值
DEFAULT_LEVEL_VALUE = os.environ.get("DEFAULT_LEVEL_VALUE", "INFO")  # 默认日志级别

# 控制台日志默认值
DEFAULT_CONSOLE_ENABLED_VALUE = os.environ.get("DEFAULT_CONSOLE_ENABLED_VALUE", "true").lower() == "true"  # 默认启用控制台日志

# 文件日志默认值
DEFAULT_FILE_ENABLED_VALUE = os.environ.get("DEFAULT_FILE_ENABLED_VALUE", "false").lower() == "true"  # 默认禁用文件日志
DEFAULT_FILE_DIR_VALUE = os.environ.get("DEFAULT_FILE_DIR_VALUE", os.path.expanduser("~"))  # 默认日志文件目录（用户主目录）
DEFAULT_FILE_NAME_VALUE = os.environ.get("DEFAULT_FILE_NAME_VALUE", "dubbo.log")  # 默认日志文件名
DEFAULT_FILE_MAX_BYTES_VALUE = int(os.environ.get("DEFAULT_FILE_MAX_BYTES_VALUE", 10 * 1024 * 1024))  # 默认单日志文件最大大小（10MB）
DEFAULT_FILE_INTERVAL_VALUE = int(os.environ.get("DEFAULT_FILE_INTERVAL_VALUE", 1))  # 默认日志轮换时间间隔
DEFAULT_FILE_BACKUP_COUNT_VALUE = int(os.environ.get("DEFAULT_FILE_BACKUP_COUNT_VALUE", 10))  # 默认日志文件备份数量

# --- Loki日志收集配置 --- 
LOKI_ENABLED_KEY = os.environ.get("LOKI_ENABLED_KEY", "false").lower() == "true"  # 是否启用Loki日志收集
LOKI_URL_KEY = os.environ.get("LOKI_URL_KEY", "http://127.0.0.1:3100/loki/api/v1/push")  # Loki服务器URL
LOKI_USER_KEY = os.environ.get("LOKI_USER_KEY", "")  # Loki认证用户名
LOKI_PASSWORD_KEY = os.environ.get("LOKI_PASSWORD_KEY", "")  # Loki认证密码
LOKI_TAG = os.environ.get("LOKI_TAG", "{}")  # Loki日志标签配置

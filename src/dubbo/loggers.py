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
import contextvars
import enum
import re
import threading
import uuid

from loguru import logger

from dubbo.configs import LoggerConfig

__all__ = ["loggerFactory"]

TRACE_ID = contextvars.ContextVar('trace_id', default='N/A')
CONTEXT_ID = contextvars.ContextVar('context_id', default='N/A')
THREAD_ID = uuid.uuid4().hex
from dubbo.monitor.loki import LokiQueueHandler

def custom_formatter(record):
    """
    统一的格式化函数
    """
    # 获取当前的 trace_id 和 content_id
    trace_id = TRACE_ID.get()
    content_id = CONTEXT_ID.get()

    # 设置到 extra 中
    record["extra"]["trace_id"] = trace_id
    record["extra"]["content_id"] = content_id

    # 构建前缀
    prefix_parts = []
    if trace_id:
        prefix_parts.append(f"[trace:{trace_id}]")
    if content_id:
        prefix_parts.append(f"[content:{content_id}]")

    # 处理前缀
    if prefix_parts:
        record["extra"]["prefix"] = " ".join(prefix_parts) + " "
    else:
        record["extra"]["prefix"] = ""

    # Handle suffix
    formatter = record["extra"].get("_formatter")
    if formatter:
        record["suffix"] = formatter.suffix
    else:
        record["suffix"] = ""

    # 返回 Loguru 格式字符串
    # 这里使用了 Loguru 的标记语言来添加颜色
    return "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<blue>{function}</blue>:<yellow>{line}</yellow> - <level>{extra[prefix]}{message}</level>\n"


class _LoggerFactory:
    """
    The logger factory.
    """

    DEFAULT_LOGGER_NAME = "dubbo"

    _logger_lock = threading.RLock()
    _config: LoggerConfig = LoggerConfig()
    _loggers = {}
    _configured = False
    _logger_id = None

    @classmethod
    def set_config(cls, config):
        if not isinstance(config, LoggerConfig):
            raise TypeError("config must be an instance of LoggerConfig")

        cls._config = config
        cls._refresh_config()

    @classmethod
    def _refresh_config(cls) -> None:
        """
        Refresh the logger configuration.
        """
        with cls._logger_lock:
            # Remove all handlers if already configured
            if cls._logger_id is not None:
                logger.remove(cls._logger_id)

            config = cls._config

            # Add console handler if enabled
            if config.is_console_enabled():
                cls._add_console_handler()

            # Add file handler if enabled
            if config.is_file_enabled():
                cls._add_file_handler()

            # Add loki handler if enabled
            if config.is_loki_enabled():
                cls._add_loki_handler()

            cls._configured = True

    @classmethod
    def _add_console_handler(cls) -> None:
        """
        Add the console handler
        """
        config = cls._config

        # Add handler with custom format function
        cls._logger_id = logger.add(
            sink=lambda msg: print(msg, end=""),
            format=custom_formatter,
            level=config.level,
        )

    @classmethod
    def _add_file_handler(cls) -> None:
        """
        Add the file handler
        """
        config = cls._config

        # Create no-color formatter

        # Add handler with custom format function
        logger.add(
            sink=config.file_config.file_name,
            format=custom_formatter,
            level=config.level,
            encoding="utf-8"
        )

    @classmethod
    def _add_loki_handler(cls) -> None:
        """
        Add the loki handler
        """
        config = cls._config

        loki_uploader_handler = LokiQueueHandler(
            upload_url=config.get_loki_config().url,
            tags=config.get_loki_config().tag,
            auth=(config.get_loki_config().user, config.get_loki_config().password)
            if all((config.get_loki_config().user, config.get_loki_config().password))
            else None,
        )

        # Add handler for Loki
        logger.add(
            sink=loki_uploader_handler,
            format=custom_formatter,
            level=config.level
        )

    @classmethod
    def get_logger(cls, name=DEFAULT_LOGGER_NAME):
        """
        Get the logger. class method.

        :return: The logger adapter.
        """
        logger_adapter = cls._loggers.get(name)
        if logger_adapter is not None:
            return logger_adapter

        with cls._logger_lock:
            logger_adapter = cls._loggers.get(name)
            # double check
            if logger_adapter is not None:
                return logger_adapter

            logger_adapter = logger.bind(name=name)
            cls._loggers[name] = logger_adapter

        return logger_adapter

# expose loggerFactory
loggerFactory = _LoggerFactory
loggerFactory.set_config(LoggerConfig())
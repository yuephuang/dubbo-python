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
from typing import Optional
from loguru import logger
from dubbo.configs import LoggerConfig

__all__ = ["loggerFactory"]

TRACE_ID = contextvars.ContextVar('trace_id', default='N/A')
CONTEXT_ID = contextvars.ContextVar('context_id', default='N/A')

from dubbo.monitor.loki import LokiQueueHandler


class ColorFormatter:
    """
    A formatter with color.
    It will format the log message like this:
    2024-06-24 16:39:57 | DEBUG | test_logger_factory:test_with_config:44 - [Dubbo] debug log
    """

    @enum.unique
    class Colors(enum.Enum):
        """
        Colors for log messages.
        """

        END = "\033[0m"
        BOLD = "\033[1m"
        BLUE = "\033[34m"
        GREEN = "\033[32m"
        PURPLE = "\033[35m"
        CYAN = "\033[36m"
        RED = "\033[31m"
        YELLOW = "\033[33m"
        GREY = "\033[38;5;240m"

    COLOR_LEVEL_MAP = {
        "DEBUG": Colors.BLUE.value,
        "INFO": Colors.GREEN.value,
        "WARNING": Colors.YELLOW.value,
        "ERROR": Colors.RED.value,
        "CRITICAL": Colors.RED.value + Colors.BOLD.value,
    }

    DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

    LOG_FORMAT: str = (
        f"{Colors.GREEN.value}{{time:YYYY-MM-DD HH:mm:ss}}{Colors.END.value}"
        " | "
        "{{level_color}}{{level: <7}}{{end_color}}"
        " | "
        f"{Colors.CYAN.value}{{extra[trace_id]}}:{{name}}:{{function}}:{{line}}{Colors.END.value}"
        " - "
        f"{Colors.PURPLE.value}[Dubbo]{Colors.END.value} "
        "{{suffix}}"
        "{{message_color}}{{message}}{{end_color}}"
    )

    def __init__(self, suffix: str = ""):
        self.suffix = f"{self.Colors.PURPLE.value}[{suffix}]{self.Colors.END.value} " if suffix else ""


class NoColorFormatter:
    """
    A formatter without color.
    It will format the log message like this:
    2024-06-24 16:39:57 | DEBUG | test_logger_factory:test_with_config:44 - [Dubbo] debug log
    """

    def __init__(self, suffix: str = ""):
        color_re = re.compile(r"\033\[[0-9;]*\w")
        self.log_format = color_re.sub("", ColorFormatter.LOG_FORMAT)
        self.suffix = f"[{suffix}] " if suffix else ""


def format_record(record):
    """
    Custom format function for loguru
    """
    # Get trace_id from context vars
    record["extra"]["trace_id"] = TRACE_ID.get()
    
    # Apply coloring based on level
    level_name = record["level"].name
    colors = ColorFormatter.COLOR_LEVEL_MAP
    record["level_color"] = colors.get(level_name, "")
    record["message_color"] = colors.get(level_name, "")
    record["end_color"] = ColorFormatter.Colors.END.value
    
    # Handle suffix
    formatter = record["extra"].get("_formatter")
    if formatter:
        record["suffix"] = formatter.suffix
    else:
        record["suffix"] = ""
        
    return record


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
        
        # Create formatter
        formatter = ColorFormatter(cls.DEFAULT_LOGGER_NAME)
        
        # Add handler with custom format function
        cls._logger_id = logger.add(
            sink=lambda msg: print(msg, end=""),
            format=format_record,
            level=config.level,
            filter=lambda record: record["extra"].update({"_formatter": formatter}) or True
        )

    @classmethod
    def _add_file_handler(cls) -> None:
        """
        Add the file handler
        """
        config = cls._config
        
        # Create no-color formatter
        formatter = NoColorFormatter(cls.DEFAULT_LOGGER_NAME)
        
        # Add handler with custom format function
        logger.add(
            sink=config.file_config.file_name,
            format=format_record,
            level=config.level,
            filter=lambda record: record["extra"].update({"_formatter": formatter}) or True,
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
            format="{time} | {level: <8} | {name}:{function}:{line} - {message}",
            level=config.level
        )

    @classmethod
    def get_logger(cls, name=DEFAULT_LOGGER_NAME) -> "LoggerAdapter":
        """
        Get the logger. class method.

        :return: The logger adapter.
        :rtype: LoggerAdapter
        """
        logger_adapter = cls._loggers.get(name)
        if logger_adapter is not None:
            return logger_adapter

        with cls._logger_lock:
            logger_adapter = cls._loggers.get(name)
            # double check
            if logger_adapter is not None:
                return logger_adapter

            logger_adapter = LoggerAdapter(name)
            cls._loggers[name] = logger_adapter

        return logger_adapter


class LoggerAdapter:
    """
    Adapter to make loguru logger compatible with the previous logging.Logger interface
    """
    
    def __init__(self, name: str):
        self.name = name
        self._logger = logger.bind(name=name)

    def _log(self, level: str, msg, *args, **kwargs):
        # Handle args formatting
        if args:
            msg = msg % args
            
        # Add trace_id to log context
        trace_id = TRACE_ID.get()
        context_id = CONTEXT_ID.get()
        
        # Bind extra context
        log = self._logger.bind(trace_id=trace_id)
        
        # Log with appropriate level
        log.log(level.upper(), msg)
            
    def debug(self, msg, *args, **kwargs):
        self._log("DEBUG", msg, *args, **kwargs)
        
    def info(self, msg, *args, **kwargs):
        self._log("INFO", msg, *args, **kwargs)
        
    def warning(self, msg, *args, **kwargs):
        self._log("WARNING", msg, *args, **kwargs)
        
    def error(self, msg, *args, **kwargs):
        self._log("ERROR", msg, *args, **kwargs)
        
    def critical(self, msg, *args, **kwargs):
        self._log("CRITICAL", msg, *args, **kwargs)
        
    def setLevel(self, level):
        # Loguru handles levels differently, this is just for compatibility
        pass


# expose loggerFactory
loggerFactory = _LoggerFactory
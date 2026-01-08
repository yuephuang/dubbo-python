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
import asyncio
import multiprocessing
import queue
import threading
from concurrent.futures import Future

from dubbo.component.nacos_client import NacosClinet
from dubbo.constants import common_constants
from dubbo.loggers import loggerFactory
from dubbo.registry import Registry, RegistryFactory
from dubbo.url import URL

_LOGGER = loggerFactory.get_logger()

try:
    multiprocessing.set_start_method('spawn', force=True)
    _LOGGER.info("Using multiprocessing.set_start_method('spawn', force=True)")
except RuntimeError:
    _LOGGER.warning("Failed to set multiprocessing start method")

DEFAULT_APPLICATION = common_constants.DEFAULT_SERVER_NAME

__all__ = [
    "NacosRegistryFactory"
]


class NacosRegistryV2:
    def __init__(self, url):
        self._url = url
        # 关键修改：初始化时不立即创建实例，或者确保实例在后台线程初始化
        self._nacos_client = None

        # 任务队列：用于主线程与后台线程通信
        self._task_queue = queue.Queue()
        self._loop = None
        self._loop_thread = None
        self._stop_event = threading.Event()
        self._loop_ready = threading.Event()

        # 启动后台处理线程
        self._start_background_worker()

        # 初始化 Nacos 客户端绑定
        self._initialize_nacos_in_loop()

    def _start_background_worker(self):
        """启动后台线程，运行事件循环并消费队列任务"""
        if self._loop_thread is not None and self._loop_thread.is_alive():
            return

        def worker():
            # 为后台线程创建私有事件循环
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # 在 Loop 所在的线程内实例化 Nacos 客户端
            # 确保其内部所有的异步组件（gRPC 等）都绑定到当前的 self._loop
            self._nacos_client = NacosClinet()

            self._loop_ready.set()

            _LOGGER.info("Nacos Background Worker Thread started.")

            # 定义一个内部处理器来消费队列
            async def queue_processor():
                while not self._stop_event.is_set():
                    try:
                        try:
                            # 从队列获取任务请求
                            item = self._task_queue.get(timeout=0.1)
                            coro_func, args, kwargs, future = item

                            try:
                                # 执行协程任务
                                result = await coro_func(*args, **kwargs)
                                if future and not future.done():
                                    future.set_result(result)
                            except Exception as e:
                                if future and not future.done():
                                    future.set_exception(e)
                                _LOGGER.error(f"Task execution error: {e}")
                            finally:
                                self._task_queue.task_done()
                        except queue.Empty:
                            continue
                    except Exception as e:
                        _LOGGER.error(f"Queue processor error: {e}")

                _LOGGER.info("Queue processor is shutting down.")

            # 启动队列处理器并运行循环
            try:
                self._loop.run_until_complete(queue_processor())
            finally:
                self._loop.close()
                _LOGGER.info("Nacos Background Loop closed.")

        self._loop_thread = threading.Thread(
            target=worker,
            name="NacosRegistryWorker",
            daemon=True
        )
        self._loop_thread.start()

        if not self._loop_ready.wait(timeout=5):
            raise RuntimeError("Failed to start Nacos background worker thread.")

    def _initialize_nacos_in_loop(self):
        """强制 Nacos 客户端在后台 Loop 中完成服务初始化"""
        _LOGGER.info("Initializing Nacos client inside background worker...")
        try:
            # 提交初始化任务
            if hasattr(self._nacos_client, 'start_init'):
                self._run_via_queue(self._nacos_client.start_init)
            else:
                self._run_via_queue(asyncio.sleep, 0)
        except Exception as e:
            _LOGGER.error(f"Failed to initialize Nacos client: {e}")

    def _run_via_queue(self, coro_func, *args, wait=True, **kwargs):
        """
        通过 Queue 提交任务请求。
        注意：传入的是协程函数及其参数，而不是已经创建的协程对象，
        以防止协程对象在错误的 Loop 线程中被预先实例化。
        """
        fut = Future()
        # 传递函数引用而非协程实例
        self._task_queue.put((coro_func, args, kwargs, fut))

        if wait:
            return fut.result()
        return fut

    def register(self, url) -> None:
        _LOGGER.info(f"V2 Registering service: {url.host}:{url.port}")
        try:
            self._run_via_queue(self._nacos_client.async_register_service, url)
        except Exception as e:
            _LOGGER.error(f"V2 Registration failed: {e}")

    def unregister(self, url) -> None:
        _LOGGER.info(f"V2 Unregistering service: {url.host}:{url.port}")
        try:
            self._run_via_queue(self._nacos_client.async_unregister_service, url)
        except Exception as e:
            _LOGGER.error(f"V2 Unregistration failed: {e}")

    def subscribe(self, url, listener) -> None:
        _LOGGER.info("V2 Subscribing to service via queue...")

        def subscribe_callback(instances):
            _LOGGER.info(f"V2 Received service notify: {len(instances)} instances")
            pass

        try:
            # 提交订阅任务
            self._run_via_queue(self._nacos_client.async_subscribe_service, subscribe_callback)
            # 立即获取一次实例
            self._run_via_queue(self._nacos_client.async_get_service)
        except Exception as e:
            _LOGGER.warning(f"V2 Subscription process failed: {e}")

    def unsubscribe(self, url, listener) -> None:
        _LOGGER.info("V2 Unsubscribing service")
        try:
            self._run_via_queue(self._nacos_client.async_unsubscribe_service, None)
        except Exception as e:
            _LOGGER.error(f"V2 Unsubscribe error: {e}")

    def lookup(self, url):
        try:
            resp = self._run_via_queue(self._nacos_client.async_get_service)
            hosts = resp.hosts if hasattr(resp, 'hosts') else []
            return hosts
        except Exception as e:
            _LOGGER.error(f"V2 Lookup failed: {e}")
            return []

    def destroy(self) -> None:
        """安全停止后台线程和队列消费"""
        _LOGGER.info("Destroying NacosRegistryV2 and stopping worker...")
        try:
            # 1. 执行清理
            if self._nacos_client and hasattr(self._nacos_client, 'async_close_config'):
                self._run_via_queue(self._nacos_client.async_close_config, wait=True)

            # 2. 触发停止信号
            self._stop_event.set()

            # 3. 等待线程结束
            if self._loop_thread:
                self._loop_thread.join(timeout=2)
        except Exception as e:
            _LOGGER.error(f"Error during registry destruction: {e}")

    def is_available(self) -> bool:
        return not self._stop_event.is_set() and self._loop_thread is not None and self._loop_thread.is_alive()


class NacosRegistryFactory(RegistryFactory):

    def get_registry(self, url: URL) -> Registry:
        # return NacosRegistry(url)
        return NacosRegistryV2(url)

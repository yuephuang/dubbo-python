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

import fcntl
import json
import os
import pathlib
import threading
from typing import List

from nacos import NacosClient
from nacos.timer import NacosTimer, NacosTimerManager

from dubbo.constants import common_constants, registry_constants
from dubbo.loggers import loggerFactory
from dubbo.registry import NotifyListener, Registry, RegistryFactory
from dubbo.url import URL, create_url

_LOGGER = loggerFactory.get_logger()

DEFAULT_APPLICATION = common_constants.DEFAULT_SERVER_NAME

__all__ = ["NacosRegistry", "NacosRegistryFactory"]


class NacosSubscriber:
    """
    Nacos instance subscriber with local cache and file lock.
    """

    def __init__(
        self, nacos_client: NacosClient, service_name: str, listener: NotifyListener
    ):
        self._nacos_client = nacos_client
        self._service_name = service_name
        self._listener = listener
        self._timer_manager = NacosTimerManager()
        self._subscribed = False

        # Define cache path: ~/.dubbo/nacos_cache/{service_name}.cache
        cache_dir = pathlib.Path.home() / ".dubbo" / "nacos_cache"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            _LOGGER.error("Failed to create nacos cache directory: %s", e)

        # Sanitize service name for filename
        safe_service_name = service_name.replace(":", "_").replace("/", "_")
        self._cache_file = cache_dir / f"{safe_service_name}.cache"

    def _save_to_local_cache(self, urls: List[URL]):
        """Save instance URLs to local file with an exclusive lock."""
        try:
            url_data = [url.to_str() for url in urls]
            with open(self._cache_file, "w", encoding="utf-8") as f:
                # Apply an exclusive lock (blocking)
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    json.dump(url_data, f)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    # Release the lock
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e:
            _LOGGER.warning("Failed to save local cache for %s: %s", self._service_name, e)

    def _read_from_local_cache(self):
        """Read instance URLs from local file with a shared lock."""
        if not self._cache_file.exists():
            return []
        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                # Apply a shared lock for reading
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    url_data = json.load(f)
                    return [create_url(u) for u in url_data]
                finally:
                    # Release the lock
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e:
            _LOGGER.warning("Failed to read local cache for %s: %s", self._service_name, e)
            return []

    def _get_server_urls(self):
        # Try to fetch from Nacos server
        instances = self._nacos_client.list_naming_instance(self._service_name)
        hosts = instances.get("hosts", [])

        new_urls = [
            URL(scheme="tri", host=h["ip"], port=h["port"])
            for h in hosts
            if h.get("enabled")
        ]

        # Success: update local cache and notify
        self._save_to_local_cache(new_urls)
        self._listener.notify(urls=new_urls)

    def refresh_instances(self):
        if not self._subscribed:
            return

        try:
            self._get_server_urls()
        except Exception as e:
            _LOGGER.error(
                "Nacos server error for %s: %s. Falling back to local cache.",
                self._service_name,
                e,
            )
            # Fallback: load from local cache if Nacos is down
            cached_urls = self._read_from_local_cache()
            if cached_urls:
                self._listener.notify(urls=cached_urls)

    def subscribe(self):
        if not self._timer_manager.all_timers().get("refresh_instances"):
            self._timer_manager.add_timer(
                NacosTimer("refresh_instances", self.refresh_instances, interval=7)
            )
            self._timer_manager.execute()
        self._subscribed = True
        # Initial refresh: also handled by exception catch
        self.refresh_instances()

    def unsubscribe(self):
        self._subscribed = False


def _init_nacos_client(url: URL) -> NacosClient:
    server_address = f"{url.host}:{url.port if url.port else 8848}"
    parameters = url.parameters

    endpoint = parameters.get("endpoint")
    namespace = parameters.get(registry_constants.NAMESPACE_KEY)
    username = url.username
    password = url.password

    return NacosClient(
        server_addresses=server_address,
        endpoint=endpoint,
        namespace=namespace,
        username=username,
        password=password,
    )


def _build_nacos_service_name(url: URL):
    service_name = url.parameters.get(common_constants.SERVICE_KEY)
    return f"{registry_constants.PROVIDERS_CATEGORY}:{service_name}"


class NacosRegistry(Registry):

    def __init__(self, url: URL):
        self._url = url
        self._nacos_client: NacosClient = _init_nacos_client(url)
        self._service_subscriber_mapping = {}

    def _service_subscriber(
        self, service_name: str, listener: NotifyListener
    ) -> NacosSubscriber:
        if service_name not in self._service_subscriber_mapping:
            self._service_subscriber_mapping[service_name] = NacosSubscriber(
                self._nacos_client, service_name=service_name, listener=listener
            )

        return self._service_subscriber_mapping[service_name]

    def register(self, url: URL) -> None:
        ip = url.host
        port = url.port
        nacos_service_name = _build_nacos_service_name(url)

        metadata = common_constants.NACOS_METAINFO
        try:
            self._nacos_client.add_naming_instance(
                nacos_service_name,
                ip,
                port,
                DEFAULT_APPLICATION,
                metadata=metadata,
                heartbeat_interval=1,
            )
        except Exception as e:
            _LOGGER.error("Failed to register to Nacos: %s", e)

    def unregister(self, url: URL) -> None:
        ip = url.host
        port = url.port
        nacos_service_name = _build_nacos_service_name(url)

        try:
            self._nacos_client.remove_naming_instance(
                nacos_service_name, ip=ip, port=port, cluster_name=DEFAULT_APPLICATION
            )
        except Exception as e:
            _LOGGER.error("Failed to unregister from Nacos: %s", e)

    def subscribe(self, url: URL, listener: NotifyListener) -> None:
        nacos_service_name = _build_nacos_service_name(url)

        subscriber = self._service_subscriber(nacos_service_name, listener)
        _LOGGER.info("Subscribing to Nacos service in background: %s", nacos_service_name)

        # Start a background thread to handle subscription tasks (initial refresh, timer setup)
        # to avoid blocking the main execution flow if Nacos is slow or unreachable.
        subscriber._get_server_urls()
        subscribe_thread = threading.Thread(
            target=subscriber.subscribe,
            name=f"NacosSubscriberThread-{nacos_service_name}",
            daemon=True
        )
        subscribe_thread.start()

    def unsubscribe(self, url: URL, listener: NotifyListener) -> None:
        nacos_service_name = _build_nacos_service_name(url)

        subscriber = self._service_subscriber(nacos_service_name, listener)
        subscriber.unsubscribe()
        listener.notify([])

    def lookup(self, url: URL):
        pass

    def get_url(self) -> URL:
        return self._url

    def is_available(self) -> bool:
        return self._nacos_client is not None

    def destroy(self) -> None:
        # stop all timers
        pass



class NacosRegistryFactory(RegistryFactory):

    def get_registry(self, url: URL) -> Registry:
        return NacosRegistry(url)
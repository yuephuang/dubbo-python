#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author:      huangyuepeng
@Project:     dubbo-demo
@File:        metadata.py
@Description: 
@Create Date: 2025/7/7 11:37
"""
import uuid
from datetime import datetime
from typing import Dict

from dubbo.lawgenesis_proto import lawgenesis_pb2

class LawAuthInfo:
    def __init__(self, auth: lawgenesis_pb2.Auth):
        self.auth = auth

    @property
    def auth_type(self):

        return self.auth.AUTY

    @property
    def auth_id(self):
        return self.auth.ACID

    @property
    def auth_key(self):
        return self.auth.ACKY

class LawMetaData:
    def __init__(self, basedata: lawgenesis_pb2.BaseData):
        """
        Initializes MetaData with a lawgenesis_pb2.BaseData object.
        Performs validation and fills in default values if missing.
        """
        if not isinstance(basedata, lawgenesis_pb2.BaseData):
            raise TypeError("basedata must be an instance of lawgenesis_pb2.BaseData")
        print(basedata)
        self._baseData = basedata
        self.validate()

    def validate(self):
        """
        Validates and populates default values for BaseData fields if they are missing.
        - VER: Protocol version, defaults to Setting.LAWGENESIS_VERSION.
        - TRID: Trace ID, defaults to a new UUID.
        - TRST: Trace Start Time (timestamp in ms), defaults to current time.
        """
        self._baseData.VER = getattr(self._baseData, 'VER', None) or ""
        self._baseData.TRID = getattr(self._baseData, 'TRID', None) or uuid.uuid4().hex
        self._baseData.TRST = getattr(self._baseData, 'TRST', None) or int(datetime.now().timestamp() * 1000)

    @property
    def basedata(self) -> lawgenesis_pb2.BaseData:
        """Returns the raw lawgenesis_pb2.BaseData object."""
        self._baseData.VER = self.version or "1.0"
        self._baseData.CBUR = self.callback_url or ""
        self._baseData.SLA = self.sla_level or 0
        self._baseData.DTYP = self.data_type or "json"

        return self._baseData

    @property
    def version(self) -> str:
        """Returns the protocol version (VER)."""
        return self._baseData.VER

    @property
    def trace_id(self) -> str:
        """Returns the entire process's unique ID (TRID)."""
        return self._baseData.TRID

    @trace_id.setter
    def trace_id(self, value: str) -> None:
        """Sets the entire process's unique ID (TRID)."""
        self._baseData.TRID = value

    @property
    def trace_start_time(self) -> int:
        """Returns the earliest data generation time in milliseconds (TRST)."""
        return self._baseData.TRST

    @property
    def expire_time(self) -> int:
        """Returns the expected timeout time in milliseconds (EXPT)."""
        return self._baseData.EXPT

    @property
    def echo_fields(self) -> Dict[str, str]:
        """Returns the echo fields (ECHO) as a dictionary."""
        return self._baseData.ECHO

    @echo_fields.setter
    def echo_fields(self, value: Dict[str, str]) -> None:
        """Sets the echo fields (ECHO) from a dictionary."""
        self._baseData.ECHO = value

    @property
    def callback_url(self) -> str:
        """Returns the callback URL (CBUR)."""
        return self._baseData.CBUR

    @callback_url.setter
    def callback_url(self, value: str) -> None:
        """Sets the callback URL (CBUR)."""
        self._baseData.CBUR = value

    @property
    def sla_level(self) -> int:
        """Returns the SLA service level (SLA)."""
        return self._baseData.SLA

    @property
    def is_retry(self) -> bool:
        """Returns whether the request is a ret"""
        return self._baseData.RETRY

    @is_retry.setter
    def is_retry(self, value: bool):
        self._baseData.RETRY = value

    @property
    def is_cache(self) -> bool:
        """Returns whether the request is a cache"""
        return self._baseData.CACHE

    @is_cache.setter
    def is_cache(self, value: bool) -> None:
        """Sets the cache flag (CACHE)."""
        self._baseData.CACHE = value

    @property
    def data_type(self) -> str:
        """Returns the data type (DTYP)."""
        return self._baseData.DTYP

    @data_type.setter
    def data_type(self, value: str) -> None:
        """Sets the data type (DTYP)."""
        self._baseData.DTYP = value

    @property
    def extra_info(self) -> Dict[str, str]:
        """Returns the additional reserved fields (EXIF) as a dictionary."""
        return self._baseData.EXIF

    @property
    def auth(self) -> LawAuthInfo:
        """Returns the authentication information (AUTH)."""
        return self._baseData.AUTH

    @auth.setter
    def auth(self, value: lawgenesis_pb2.Auth) -> None:
        """Sets the authentication information (AUTH)."""
        self._baseData.AUTH.ACID = value.ACID
        self._baseData.AUTH.ACKY = value.ACKY
        self._baseData.AUTH.AUTY = value.AUTY

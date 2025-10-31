#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author:      huangyuepeng
@Project:     lawgenesis_sdk
@File:        __init__.py
@Description: 
@Create Date: 2025/7/8 14:28
"""
from .lawgenesis_proto import LLMProtobuf, FileProtobuf, TxtProtobuf, ProtobufInterface, ResponseProto
from .metadata import LawMetaData, LawAuthInfo

__all__ = ["LLMProtobuf", "FileProtobuf", "TxtProtobuf", "ProtobufInterface", "LawMetaData", "LawAuthInfo", "ResponseProto"]
import hashlib
from typing import Optional, List, Any

import orjson


class ProtobufInterface:
    def __init__(self, json: dict=None):
        """
        Args:
            json:
        """
        self._json = json
        if isinstance(json, bytes):
            self._json = orjson.loads(json)
        if not isinstance(self._json, dict):
            raise TypeError("json must be dict")
        self._key = None
    @property
    def protobuf_type(self):
        return "base"

    @property
    def cache_key(self) -> str:
        # 如果没有设置key, 则自己生成key
        if self._key is None:
            if "cache_key" in self.json:
                self._key = self.json.get("cache_key")
            else:
                data = self.param2json
                data.pop("contextId", None)
                self._key = hashlib.md5(orjson.dumps(data)).hexdigest()
        return self._key

    @cache_key.setter
    def cache_key(self, value: str) -> None:
        self._key = value

    @property
    def json(self) -> dict:
        return self._json

    @json.setter
    def json(self, value: dict) -> None:
        self._json = value

    @property
    def context_id(self) -> Optional[str]:
        """Context ID for historical data."""
        return self.json.get("contextId", "")

    @property
    def cmd_params(self) -> Optional[dict]:
        """Extra information, wrapped in an ExtraInfo object."""
        cmd_params_data = self.json.get("cmdParams", {})
        return cmd_params_data

    @property
    def ugc_content(self) -> Optional[str]:
        """User-generated content."""
        return self.json.get("ugcContent", "")

    @property
    def param2json(self) -> dict:
        """
        这个主要是将必须得参数转换为json，保证传输数据的最小化
        Returns:
            必须的参数，转换为json
        """
        return self.json

    @property
    def param2bytes(self) -> bytes:
        """
        这个主要是将必须得参数转换为bytes，保证传输数据最 efficiency
        Returns:
            必须的参数，转换为bytes
        """
        # 新增cache_key 传输
        send_data = self.param2json
        send_data["cache_key"] = self.cache_key
        return orjson.dumps(send_data)



class LLMProtobuf(ProtobufInterface):
    @property
    def protobuf_type(self):
        return "llm"

    @property
    def model_name(self) -> Optional[str]:
        """Model name."""
        return self.json.get("model_name")

    @property
    def messages(self) -> Optional[list[dict]]:
        """Messages."""
        return self.json.get("messages")

    @property
    def param2json(self):
        return {
            "model_name": self.model_name,
            "messages": self.messages,
            "contextId": self.context_id,
        }

class TxtProtobuf(ProtobufInterface):
    @property
    def protobuf_type(self):
        return "txt"

    @property
    def param2json(self):
        return {
            "ugcContent": self.ugc_content,
            "contextId": self.context_id,
            "cmdParams": self.cmd_params,
        }

class FileListStruct(object):
    def __init__(self, file_struct: dict):
        self._file_struct = file_struct

    @property
    def file(self) -> str:
        return self._file_struct.get("file")

    @property
    def filetype(self) -> str:
        return self._file_struct.get("filetype")

    @property
    def extraInfo(self) -> dict:
        return self._file_struct.get("extraInfo", {})

    @property
    def to_json(self) -> dict:
        return {
            "file": self.file,
            "filetype": self.filetype,
            "extraInfo": self.extraInfo,
        }

class FileProtobuf(ProtobufInterface):
    @property
    def protobuf_type(self):
        return "file"

    @property
    def fileList(self) -> Optional[list[FileListStruct]]:
        return [FileListStruct(file) for file in self.json.get("fileList", [])]

    @property
    def fileListJson(self) -> List[dict]:
        return [file.to_json for file in self.fileList]

    @property
    def param2json(self) -> dict:
        return {
            "fileList": self.fileListJson,
            "ugcContent": self.ugc_content,
            "contextId": self.context_id,
            "cmdParams": self.cmd_params,
        }

class ResponseProto:
    def __init__(self, data: Any=None, context_id: str="", code=None):
        self._data = data
        self._context_id = context_id
        self._code = code

    @property
    def to_json(self) -> dict:
        return {
            "data": self.data,
            "context_id": self.context_id,
            "code": self.code,
        }

    def to_bytes(self):
        return orjson.dumps(self.to_json)

    # 返回结果体，适配之前的数据结构
    def get(self, key, default=None):
        """
        获取当前ResponseProto中的data数据的指定key, 原因，现在是返回结构体，兼容之前的dict.get
        """

        return self.to_json.get(key, default)

    @property
    def data(self):
        return self._data

    @property
    def code(self):
        return self._code

    @property
    def context_id(self):
        return self._context_id

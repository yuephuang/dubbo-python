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
import time
from typing import List, Dict, Any

from dubbo.notify._interface import NoticeFactory, ServerMetaData


class FeiShuNotify(NoticeFactory):
    """
    FeiShuNotify
    """
    @property
    def header(self):
        return {
            "Content-Type": "application/json"
        }

    async def async_send_text(self, text):
        """
        发送文本消息
        """
        data = {
            "msg_type": "text",
            "content": {
                "text": text
            }
        }
        return await self.async_send_data(data)

    async def async_send_rich_text(self, title, content: List[List[Dict[str, str]]]):
        """
        发送富文本消息
        """
        data = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": f"服务: {self.server_name}, 标题: {title}",
                        "content": content
                    }
                }
            }
        }
        return await self.async_send_data(data)


    async def send_card(self, header: Dict[str, Any], body: List[Dict[str, Any]]):
        """
        发送卡片消息
        """
        data = {
          "msg_type": "interactive",
          "card": {
            "schema": "2.0",
            "config": {
              "update_multi": True,
              "style": {
                "text_size": {
                  "normal_v2": {
                    "default": "normal",
                    "pc": "normal",
                    "mobile": "heading"
                  }
                }
              }
            },
              "header": header,
              "body": body
        }
      }
        return await self.async_send_data(data)

    async def async_send_table(self, title="", subtitle="", elements: List[ServerMetaData] =None):
        """
        将json 数据变成表格发布
        """
        header = {
          "title": {
            "tag": "plain_text",
            "content": title
          },
          "subtitle": {
            "tag": "plain_text",
            "content": subtitle
          },
          "template": "blue",
          "padding": "12px 12px 12px 12px"
        }


        body = {
            "direction": "vertical",
            "padding": "12px 12px 12px 12px",
            "elements": [
                {
                    "tag": "table",
                    "page_size": 5,
                    "row_height": "auto",
                    "header_style": {
                        "text_align": "left",
                        "text_size": "normal",
                        "background_style": "none",
                        "text_color": "grey",
                        "bold": True,
                        "lines": 1
                    },
                    "columns": [
                        {
                            "name": "uuid",
                            "display_name": "服务id",
                            "data_type": "text",
                            "horizontal_align": "left",
                            "vertical_align": "top",
                            "width": "auto"
                        },
                        {
                            "name": "server_name",
                            "display_name": "服务名称",
                            "data_type": "text",
                            "horizontal_align": "left",
                            "vertical_align": "top",
                            "width": "auto"
                        },
                        {
                            "name": "host",
                            "display_name": "Ip",
                            "data_type": "text",
                            "horizontal_align": "left",
                            "vertical_align": "top",
                            "width": "auto"
                        },
                        {
                            "name": "host_name",
                            "display_name": "主机名",
                            "data_type": "text",
                            "horizontal_align": "left",
                            "vertical_align": "top",
                            "width": "auto"
                        },
                        {
                            "name": "intranet_ip",
                            "display_name": "内网ip",
                            "data_type": "text",
                            "horizontal_align": "left",
                            "vertical_align": "top",
                            "width": "auto"
                        },
                        {
                            "name": "internet_ip",
                            "display_name": "外网ip",
                            "data_type": "text",
                            "horizontal_align": "left",
                            "vertical_align": "top",
                            "width": "auto"
                        },
                        {
                            "name": "message",
                            "display_name": "消息",
                            "data_type": "text",
                            "horizontal_align": "left",
                            "vertical_align": "top",
                            "width": "auto"
                        },
                        {
                            "name": "start_time",
                            "display_name": "启动时间",
                            "data_type": "text",
                            "horizontal_align": "left",
                            "vertical_align": "top",
                            "width": "auto"
                        },
                    ],
                    "rows": [item.json for item in elements]
                }
            ]
        }
        return await self.send_card(header=header, body=body)

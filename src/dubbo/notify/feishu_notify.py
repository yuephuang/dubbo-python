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
from typing import List, Dict

from dubbo.notify._interface import NoticeFactory

class FeiShuNotify(NoticeFactory):
    """
    FeiShuNotify
    """
    @property
    def header(self):
        return {
            "Content-Type": "application/json"
        }

    async def send_text(self, text):
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

    async def send_rich_text(self, title, content: List[List[Dict[str, str]]]):
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


import asyncio
import datetime
from dubbo.notify import FeiShuNotify, ServerMetaData


feishu = FeiShuNotify(url="https://open.feishu.cn/open-apis/bot/v2/hook/46b7d659-b238-4098-910d-c86b0aa79bda", header={}, server_name="test")

content = [
                    [{
                        "tag": "text",
                        "text": "项目有更新: "
                    }, {
                        "tag": "a",
                        "text": "请查看",
                        "href": "http://www.example.com/"
                    }, {
                        "tag": "at",
                        "user_id": "ou_18eac8********17ad4f02e8bbbb"
                    }]
                ]

data_list = {f"i": i for i in range(10)}
async def main():
    # await feishu.send_text("hello world")
    # await feishu.send_rich_text(title="test", content=content)
    # await feishu.send_card(header={}, body={})
    server_notify_data = ServerMetaData(server_name="test", status="进行中", start_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), host="127.0.0.1", port=8080, intranet_ip="127.0.0.1", internet_ip="127.0.0.1")


    await feishu.async_send_table(title="test", subtitle="test", elements=[server_notify_data])

if __name__ == '__main__':
    asyncio.run(main())
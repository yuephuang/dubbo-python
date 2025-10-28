import asyncio

from dubbo.notify import FeiShuNotify


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

async def main():
    await feishu.send_text("hello world")
    await feishu.send_rich_text(title="test", content=content)

if __name__ == '__main__':
    asyncio.run(main())
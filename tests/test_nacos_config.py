import time

from dubbo.configcenter.nacos.nacos_configcenter import NacosConfigCenter
from dubbo.url import URL, create_url

url = create_url("nacos://nacos:123456@127.0.0.1:8848?namespace=autodl-poc")

nacos_client = NacosConfigCenter(url)

async def config_listener(tenant, data_id, group, content):
    print("listen, tenant:{} data_id:{} group:{} content:{}".format(tenant, data_id, group, content))


async def test_nacos_config():
    content = await nacos_client.async_get_config("test", "test")
    return content

async def test_nacos_config_subscribe():
    content = await nacos_client.async_subscribe("test", "test", config_listener)
    return content

async def test_nacos_config_unsubscribe():
    content = await nacos_client.async_unsubscribe("test", "test", config_listener)
    return content

async def test_nacos_config_publish(content):
    content = await nacos_client.async_publish_config("test", "test", content=content)
    return content

async def test_nacos_config_close():
    content = await nacos_client.async_close()
    return content

async def main():
    # data = await test_nacos_config()
    # print(data)
    # assert data == "hello world"
    # msg = "hello world1"
    # data = await test_nacos_config_publish(content=msg)
    # assert data
    # data = await test_nacos_config()
    # assert data == "hello world1"
    # msg = "hello world"
    # data = await test_nacos_config_publish(content=msg)
    # assert data
    await test_nacos_config_subscribe()
    while True:
        await asyncio.sleep(1) # 允许事件循环继续运行





if __name__ == '__main__':
    import asyncio

    data1 = asyncio.run(main())
    print(data1)
    #
    #
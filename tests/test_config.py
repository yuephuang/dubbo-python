import asyncio
import os
os.environ["NACOS_CONFIG_URL"] = "nacos://nacos:123456@127.0.0.1:8848?namespace=autodl-poc"
from  dubbo.constants._interfaces import ConfigReloader

class ConfigReloaderImpl(ConfigReloader):
    def config_name(self):
        return "CommonConstants"

    def group(self):
        return "config"



ca = ConfigReloaderImpl()

async def main():
    while True:
        print(ca.DUBBO_VALUE)
        await asyncio.sleep(1) # 允许事件循环继续运行


if __name__ == '__main__':
    asyncio.run(main())
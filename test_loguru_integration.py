import threading
import time
from dubbo.loggers import loggerFactory, TRACE_ID
from dubbo.configs import LoggerConfig

def test_loguru_integration():
    # 测试基础日志功能
    logger = loggerFactory.get_logger("test_logger")
    logger.info("这是一个测试日志消息")
    logger.error("这是一个错误消息")
    logger.debug("这是一个调试消息")
    
    # 测试上下文变量
    TRACE_ID.set("test-trace-id-123")
    logger.info("这条消息应该包含trace_id")
    
    # 测试不同名称的logger
    another_logger = loggerFactory.get_logger("another_logger")
    another_logger.warning("来自另一个logger的消息")
    
    print("基础功能测试完成")

def test_thread_safety():
    def worker(thread_id):
        TRACE_ID.set(f"trace-{thread_id}")
        logger = loggerFactory.get_logger(f"thread-{thread_id}")
        for i in range(5):
            logger.info(f"线程 {thread_id} 的第 {i} 条消息")
            time.sleep(0.1)
    
    # 创建多个线程测试线程安全性
    threads = []
    for i in range(3):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    # 等待所有线程完成
    for t in threads:
        t.join()
    
    print("线程安全测试完成")

def test_config_change():
    # 测试配置更改
    config = LoggerConfig()
    config.level = "DEBUG"
    loggerFactory.set_config(config)
    
    logger = loggerFactory.get_logger("config_test")
    logger.debug("配置更改后的调试消息")
    
    print("配置更改测试完成")

if __name__ == "__main__":
    print("开始测试 loguru 集成...")
    
    # 先进行基础测试
    test_loguru_integration()
    
    # 测试线程安全
    test_thread_safety()
    
    # 测试配置更改
    test_config_change()
    
    print("所有测试完成!")
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

def setup_logger():
    # 创建日志目录
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 配置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建两个处理器：一个用于控制台输出，一个用于文件输出
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # 使用 RotatingFileHandler 进行日志轮转
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, f'app_{datetime.now().strftime("%Y%m%d")}.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    # 获取根日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 添加处理器
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger 
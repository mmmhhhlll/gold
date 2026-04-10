# ============================================
# 日志工具 (Logger Utility)
# ============================================

import logging
import os
from datetime import datetime


def setup_logger(
    name: str = "trading",
    level: str = "INFO",
    log_dir: str = "logs"
) -> logging.Logger:
    """
    配置并返回日志器
    
    :param name: 日志器名称
    :param level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
    :param log_dir: 日志文件目录
    :return: 配置好的 Logger
    """
    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)
    
    # 日志文件名（按日期）
    log_file = os.path.join(log_dir, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")
    
    # 创建日志器
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # 避免重复添加 handler
    if not logger.handlers:
        # 文件 Handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # 控制台 Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, level.upper()))
        
        # 格式
        formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    return logger


# 全局默认日志器
default_logger = setup_logger()


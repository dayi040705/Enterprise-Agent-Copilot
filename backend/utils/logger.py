"""
日志系统 — 双通道输出: 控制台 (开发调试) + 文件 (持久化留存)

日志级别: DEBUG < INFO < WARNING < ERROR
  开发时看控制台 → 彩色高亮, 快速定位问题
  线上排查看文件 → 持久化, 可按时间回溯

文件位置: backend/logs/rag_YYYY-MM-DD.log
  每天自动轮转, 保留最近 30 天
"""
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logger(
    name: str = "rag-assistant",
    log_dir: str = "./logs",
    level: int = logging.INFO,
) -> logging.Logger:
    """
    创建双通道 logger:
      1. 控制台 (StreamHandler) — 开发调试用
      2. 文件 (TimedRotatingFileHandler) — 每天一个文件, 保留 30 天
    """

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 (uvicorn reload 时会重新加载模块)
    if logger.handlers:
        return logger

    # 日志格式: [时间] [级别] [模块] 消息
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 通道1: 控制台
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)  # 控制台打印所有级别
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 通道2: 文件 (每天轮转)
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    file_handler = TimedRotatingFileHandler(
        filename=log_path / "rag.log",
        when="midnight",     # 每天午夜轮转
        interval=1,
        backupCount=30,      # 保留最近 30 天
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)   # 文件只记录 INFO 及以上
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# 全局 logger 实例 — 所有模块 import 这一个
logger = setup_logger()

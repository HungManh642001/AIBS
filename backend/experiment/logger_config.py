import logging
import sys
import os
from logging.handlers import RotatingFileHandler

# Create logging folder
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger(service_name, log_file_name=None):
    """
    Hàm này tạo ra một logger chuẩn cho toàn bộ hệ thống.
    Nó sẽ ghi log ra 2 nơi:
    1. Màn hình Console (để Electron bắt được và hiện lên Terminal)
    2. File .log (để lưu trữ lâu dài)
    """
    if log_file_name is None:
        log_file_name = f'{service_name.lower()}.log'

    logger = logging.getLogger(service_name)
    logger.setLevel(logging.DEBUG)

    if logger.hasHandlers():
        return logger
    
    formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)

    file_path = os.path.join(LOG_DIR, log_file_name)
    file_handler = RotatingFileHandler(file_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    # logger.propagate = False
    return logger
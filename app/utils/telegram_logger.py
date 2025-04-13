import os
import logging
import requests
import traceback
import platform
from logging import Handler, LogRecord
from dotenv import load_dotenv

load_dotenv()

class TelegramHandler(Handler):
    def __init__(self):
        super().__init__()
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not self.bot_token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
        
        # 确保chat_id是数字或以@开头的字符串
        if not (str(self.chat_id).startswith('@') or str(self.chat_id).lstrip('-').isdigit()):
            raise ValueError(f"Invalid chat_id format: {self.chat_id}. Must be a number or start with @")
        
        # 验证bot token和chat_id
        self.verify_credentials()
            
    def verify_credentials(self):
        """验证bot token和chat_id是否有效"""
        try:
            # 首先测试bot token是否有效
            url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                error_info = response.json() if response.text else "No error details"
                raise ValueError(f"Invalid bot token. Response: {error_info}")
            
            # 测试发送消息
            test_message = "🤖 Bot connection test"
            self.send_message(test_message, is_test=True)
            print(f"Successfully connected to Telegram bot and chat: {self.chat_id}")
            
        except Exception as e:
            print(f"Telegram credentials verification failed: {str(e)}")
            print("Please ensure:")
            print("1. Your bot token is correct")
            print("2. Your chat_id is correct")
            print("3. You have started a chat with the bot")
            print("4. If using group chat_id, the bot has been added to the group")
            raise
            
    def emit(self, record: LogRecord):
        try:
            # 对于启动消息和错误消息都发送
            if record.levelno >= logging.ERROR or getattr(record, 'startup_msg', False):
                msg = self.format(record)
                
                # 如果是异常，添加堆栈跟踪
                if record.exc_info:
                    msg += f"\n\nTraceback:\n{''.join(traceback.format_exception(*record.exc_info))}"
                
                self.send_message(msg)
        except Exception:
            self.handleError(record)
    
    def send_message(self, message: str, is_test=False):
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            # 将消息分块发送，因为Telegram有消息长度限制
            max_length = 4000
            
            for i in range(0, len(message), max_length):
                chunk = message[i:i + max_length]
                data = {
                    "chat_id": self.chat_id,
                    "text": chunk
                }
                response = requests.post(url, json=data, timeout=10)
                
                if response.status_code != 200:
                    error_info = response.json() if response.text else "No error details"
                    error_msg = f"Telegram API error: Status {response.status_code}, Response: {error_info}"
                    if is_test:
                        raise ValueError(error_msg)
                    else:
                        print(error_msg)
                    return
                    
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error when sending Telegram message: {str(e)}"
            if is_test:
                raise ValueError(error_msg)
            print(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error when sending Telegram message: {str(e)}"
            if is_test:
                raise ValueError(error_msg)
            print(error_msg)

def send_startup_message(logger):
    """发送启动通知消息"""
    try:
        # 获取系统信息
        system_info = platform.system()
        python_version = platform.python_version()
        
        startup_msg = (
            "🚀 AutoTrade Bot Started\n"
            f"System: {system_info}\n"
            f"Python: {python_version}"
        )
        
        # 创建一个特殊的日志记录
        record = logging.LogRecord(
            name="startup",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=startup_msg,
            args=(),
            exc_info=None
        )
        # 添加特殊标记
        setattr(record, 'startup_msg', True)
        
        # 使用根日志记录器的处理器发送消息
        for handler in logger.handlers:
            if isinstance(handler, TelegramHandler):
                handler.emit(record)
                
    except Exception as e:
        print(f"Error sending startup message: {str(e)}")

def setup_telegram_logger():
    """设置全局日志处理器，将错误日志发送到Telegram"""
    try:
        # 创建根日志记录器
        root_logger = logging.getLogger()
        
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 添加Telegram处理器
        telegram_handler = TelegramHandler()
        telegram_handler.setFormatter(formatter)
        root_logger.addHandler(telegram_handler)
        
        # 确保根日志记录器的级别足够低以捕获所有消息
        root_logger.setLevel(logging.INFO)
        
        # 发送启动消息
        send_startup_message(root_logger)
        
    except Exception as e:
        print(f"Error setting up telegram logger: {str(e)}") 
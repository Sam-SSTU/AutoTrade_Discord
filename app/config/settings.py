from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Optional
import os

class Settings(BaseSettings):
    """应用配置设置"""
    
    # 数据库配置
    database_url: Optional[str] = Field(default=None, env="DATABASE_URL")
    postgres_user: str = Field(default="postgres", env="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", env="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="localhost", env="POSTGRES_HOST")
    postgres_port: str = Field(default="5432", env="POSTGRES_PORT")
    postgres_db: str = Field(default="autotrade", env="POSTGRES_DB")
    
    # Discord配置
    discord_token: Optional[str] = Field(default=None, env="DISCORD_TOKEN")
    
    # OpenAI配置
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    openai_api_base: str = Field(default="https://api.openai.com/v1", env="OPENAI_API_BASE")
    openai_proxy_url: str = Field(default="https://api.openai99.top/v1", env="OPENAI_PROXY_URL")
    use_openai_proxy: bool = Field(default=False, env="USE_OPENAI_PROXY")
    
    # AI处理配置
    ai_max_concurrent_workers: int = Field(default=5, env="AI_MAX_CONCURRENT_WORKERS")  # 最大并发工作器数量
    ai_max_batch_size: int = Field(default=20, env="AI_MAX_BATCH_SIZE")  # 一次处理的最大消息数
    ai_request_rate_limit: int = Field(default=10, env="AI_REQUEST_RATE_LIMIT")  # 每分钟最大API请求数
    ai_queue_max_size: int = Field(default=1000, env="AI_QUEUE_MAX_SIZE")  # 队列最大大小
    ai_processing_timeout: int = Field(default=30, env="AI_PROCESSING_TIMEOUT")  # 处理超时时间(秒)
    
    # Redis配置
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")
    
    # 应用配置
    debug: bool = Field(default=False, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    @validator('use_openai_proxy', pre=True)
    def parse_bool(cls, v):
        """解析布尔值，处理包含注释的情况"""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            # 移除注释部分
            clean_val = v.split('#')[0].strip().lower()
            if clean_val in ('true', '1', 'yes', 'on'):
                return True
            elif clean_val in ('false', '0', 'no', 'off'):
                return False
        return False
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # 忽略额外的字段

# 全局设置实例
_settings = None

def get_settings() -> Settings:
    """获取设置单例"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings 
import openai
import os
from typing import Optional, Dict, Any, List
import logging
from ..config.settings import get_settings

# 设置专门的调试日志器
logger = logging.getLogger("app.ai.openai_client")
logger.setLevel(logging.DEBUG)

# 如果还没有处理器，添加控制台处理器
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

settings = get_settings()

class OpenAIClient:
    def __init__(self):
        """初始化OpenAI客户端，支持代理配置"""
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY 环境变量未设置")
        
        # 根据配置选择API地址 - 添加调试日志，处理注释
        use_proxy_env = os.getenv("USE_OPENAI_PROXY", "false")
        proxy_url_env = os.getenv("OPENAI_PROXY_URL", "https://api.openai99.top/v1")
        
        # 清理环境变量中的注释（去掉 # 及其后面的内容）
        use_proxy_env = use_proxy_env.split('#')[0].strip()
        proxy_url_env = proxy_url_env.split('#')[0].strip()
        
        logger.info(f"环境变量读取: USE_OPENAI_PROXY={use_proxy_env}, OPENAI_PROXY_URL={proxy_url_env}")
        
        use_proxy = use_proxy_env.lower() == "true"
        logger.info(f"代理配置: use_proxy={use_proxy}")
        
        if use_proxy:
            # 代理地址处理 - 修复端点路径
            proxy_base = proxy_url_env.rstrip('/v1').rstrip('/')
            
            # 对于openai99.top等代理服务，需要使用完整的v1路径
            if 'openai99.top' in proxy_base:
                self.base_url = f"{proxy_base}/v1"
            else:
                self.base_url = proxy_base
                
            logger.info(f"使用代理模式，base_url: {self.base_url}")
        else:
            # 官方地址，只使用基础域名
            self.base_url = "https://api.openai.com"
            logger.info(f"使用官方模式，base_url: {self.base_url}")
        
        # 初始化客户端
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        logger.info(f"OpenAI客户端初始化完成，最终使用地址: {self.base_url}")
    
    def _get_default_analysis(self, reason: str = "处理失败") -> Dict[str, Any]:
        """返回默认的分析结果，用于错误处理"""
        return {
            "is_trading_related": False,
            "priority": 1,
            "keywords": [],
            "category": "其他",
            "urgency": "低",
            "sentiment": "中性",
            "confidence": 0.0,
            "summary": reason,
            "error": reason
        }
    
    async def analyze_message(self, message_content: str, context_messages: List[str] = None) -> Dict[str, Any]:
        """
        使用GPT-4o分析单条消息
        
        Args:
            message_content: 要分析的消息内容
            context_messages: 上下文消息列表
            
        Returns:
            Dict包含分析结果：
            - is_trading_related: 是否与交易相关
            - priority: 优先级 (1-5, 5最高)
            - keywords: 提取的关键词
            - category: 消息分类
            - urgency: 紧急程度
            - sentiment: 情感倾向
        """
        try:
            # 构建分析提示词
            system_prompt = """你是一个专业的加密货币交易消息分析师。你的任务是分析KOL消息，判断是否与交易相关，并提取关键信息。

请按照以下格式返回JSON结果：
{
    "is_trading_related": true/false,
    "priority": 1-5的整数,
    "keywords": ["关键词1", "关键词2"],
    "category": "交易信号/市场分析/技术分析/新闻资讯/闲聊/其他",
    "urgency": "低/中/高",
    "sentiment": "看涨/看跌/中性",
    "confidence": 0.0-1.0的置信度,
    "summary": "简短的消息摘要"
}

判断标准：
1. 交易相关：包含币种名称、价格、技术指标、买卖建议、市场分析等
2. 优先级：5=立即买卖信号，4=重要分析，3=一般信息，2=参考信息，1=闲聊
3. 紧急程度：基于时效性和重要性判断
4. 情感：基于对市场的看法判断"""

            # 构建用户消息
            user_message = f"分析以下消息：\n\n{message_content}"
            
            # 如果有上下文，添加上下文信息
            if context_messages:
                context_text = "\n".join(context_messages[-3:])  # 只取最近3条
                user_message += f"\n\n上下文消息：\n{context_text}"
            
            logger.info(f"正在调用OpenAI API: {self.base_url}")
            logger.debug(f"使用API Key: {self.api_key[:10]}...")  # 只显示前10个字符
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            # 添加调试信息
            logger.debug(f"API响应类型: {type(response)}")
            logger.debug(f"API响应属性: {dir(response)}")
            
            # 处理不同格式的响应
            result = None
            if hasattr(response, 'choices') and response.choices:
                result = response.choices[0].message.content
                logger.debug(f"从choices提取内容: {result}")
            elif isinstance(response, str):
                # 某些代理可能直接返回字符串
                result = response
                logger.debug(f"直接使用字符串响应: {result}")
            elif hasattr(response, 'content'):
                result = response.content
                logger.debug(f"从content属性提取: {result}")
            else:
                logger.error(f"未知的响应格式: {type(response)}, 内容: {response}")
                raise ValueError(f"API返回了未知格式的响应: {type(response)}")
            
            # 检查响应内容是否为空
            if not result or result.strip() == "":
                logger.error("API返回了空响应")
                raise ValueError("API返回了空响应")
            
            # 检查是否返回了HTML页面（说明API配置有问题）
            if result.strip().lower().startswith('<!doctype html>') or result.strip().lower().startswith('<html'):
                logger.error("API返回了HTML页面而不是JSON，可能的原因：")
                logger.error("1. API Key无效或未配置")
                logger.error("2. 代理服务配置错误")
                logger.error("3. 请求端点路径不正确")
                logger.error(f"当前使用的base_url: {self.base_url}")
                logger.error(f"当前使用的API Key前缀: {self.api_key[:20]}...")
                
                # 返回默认分析而不是抛出异常
                analysis = self._get_default_analysis("API配置错误：返回HTML页面")
                logger.info(f"消息分析完成: 交易相关={analysis.get('is_trading_related')}, 优先级={analysis.get('priority')}")
                return analysis
            
            # 尝试清理响应内容（移除可能的非JSON前缀）
            result = result.strip()
            if result.startswith('```json'):
                result = result[7:]  # 移除 ```json 前缀
            if result.endswith('```'):
                result = result[:-3]  # 移除 ``` 后缀
            result = result.strip()
            
            logger.debug(f"清理后的响应内容: {result}")
            
            # 解析JSON
            import json
            try:
                analysis = json.loads(result)
            except json.JSONDecodeError as je:
                logger.error(f"JSON解析失败: {je}")
                logger.error(f"原始响应内容: '{result}'")
                logger.error(f"响应内容长度: {len(result)}")
                logger.error(f"响应内容字节: {result.encode('utf-8')}")
                
                # 尝试修复常见的JSON格式问题
                if result:
                    # 尝试寻找JSON对象
                    start_idx = result.find('{')
                    end_idx = result.rfind('}')
                    if start_idx != -1 and end_idx != -1:
                        json_part = result[start_idx:end_idx+1]
                        logger.debug(f"尝试解析提取的JSON部分: {json_part}")
                        try:
                            analysis = json.loads(json_part)
                        except json.JSONDecodeError:
                            logger.error("提取的JSON部分也无法解析")
                            # 使用默认分析结果而不是抛出异常
                            logger.warning("使用默认分析结果作为备用方案")
                            analysis = self._get_default_analysis("JSON解析失败")
                    else:
                        logger.error("未能在响应中找到JSON对象")
                        analysis = self._get_default_analysis("未找到JSON对象")
                else:
                    logger.error("响应内容为空")
                    analysis = self._get_default_analysis("响应内容为空")
            
            logger.info(f"消息分析完成: 交易相关={analysis.get('is_trading_related')}, 优先级={analysis.get('priority')}")
            return analysis
            
        except Exception as e:
            logger.error(f"OpenAI消息分析失败: {str(e)}")
            # 返回默认分析结果
            return self._get_default_analysis(f"分析失败: {str(e)}")
    
    async def extract_trading_signals(self, message_content: str, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从交易相关消息中提取具体的交易信号
        
        Args:
            message_content: 消息内容
            analysis: 之前的分析结果
            
        Returns:
            Dict包含交易信号信息或None
        """
        if not analysis.get("is_trading_related") or analysis.get("priority", 1) < 4:
            return None
            
        try:
            system_prompt = """你是交易信号提取专家。从KOL消息中提取具体的交易信号信息。

返回JSON格式：
{
    "has_signal": true/false,
    "signal_type": "买入/卖出/持有/观察",
    "symbols": ["BTC", "ETH"],
    "target_price": "目标价格或null",
    "stop_loss": "止损价格或null", 
    "entry_price": "入场价格或null",
    "time_frame": "时间周期",
    "reasoning": "交易理由",
    "risk_level": "低/中/高"
}"""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"提取交易信号：\n{message_content}"}
                ],
                temperature=0.2,
                max_tokens=300,
                response_format={"type": "json_object"}
            )
            
            # 添加调试信息
            logger.debug(f"交易信号API响应类型: {type(response)}")
            
            # 处理不同格式的响应
            result = None
            if hasattr(response, 'choices') and response.choices:
                result = response.choices[0].message.content
                logger.debug(f"从choices提取交易信号内容: {result}")
            elif isinstance(response, str):
                # 某些代理可能直接返回字符串
                result = response
                logger.debug(f"直接使用字符串响应: {result}")
            elif hasattr(response, 'content'):
                result = response.content
                logger.debug(f"从content属性提取: {result}")
            else:
                logger.error(f"未知的响应格式: {type(response)}, 内容: {response}")
                raise ValueError(f"API返回了未知格式的响应: {type(response)}")
            
            # 检查响应内容是否为空
            if not result or result.strip() == "":
                logger.error("交易信号API返回了空响应")
                raise ValueError("API返回了空响应")
            
            # 尝试清理响应内容（移除可能的非JSON前缀）
            result = result.strip()
            if result.startswith('```json'):
                result = result[7:]  # 移除 ```json 前缀
            if result.endswith('```'):
                result = result[:-3]  # 移除 ``` 后缀
            result = result.strip()
            
            logger.debug(f"清理后的交易信号响应内容: {result}")
            
            # 解析JSON
            import json
            try:
                signal = json.loads(result)
            except json.JSONDecodeError as je:
                logger.error(f"交易信号JSON解析失败: {je}")
                logger.error(f"原始响应内容: '{result}'")
                logger.error(f"响应内容长度: {len(result)}")
                
                # 尝试修复常见的JSON格式问题
                if result:
                    # 尝试寻找JSON对象
                    start_idx = result.find('{')
                    end_idx = result.rfind('}')
                    if start_idx != -1 and end_idx != -1:
                        json_part = result[start_idx:end_idx+1]
                        logger.debug(f"尝试解析提取的JSON部分: {json_part}")
                        try:
                            signal = json.loads(json_part)
                        except json.JSONDecodeError:
                            logger.error("提取的JSON部分也无法解析")
                            raise
                    else:
                        logger.error("未能在响应中找到JSON对象")
                        raise
                else:
                    logger.error("响应内容为空")
                    raise
            
            logger.info(f"交易信号提取完成: {signal.get('signal_type')} {signal.get('symbols')}")
            return signal
            
        except Exception as e:
            logger.error(f"交易信号提取失败: {str(e)}")
            return None

# 全局客户端实例
openai_client = None

def get_openai_client() -> OpenAIClient:
    """获取OpenAI客户端单例"""
    global openai_client
    if openai_client is None:
        openai_client = OpenAIClient()
    return openai_client 
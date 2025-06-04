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
        
        # 根据配置选择API地址 - 修复环境变量处理
        use_proxy_env = os.getenv("USE_OPENAI_PROXY", "false")
        proxy_url_env = os.getenv("OPENAI_PROXY_URL", "https://api.openai99.top/v1")
        
        # 清理环境变量中的注释（去掉 # 及其后面的内容）
        use_proxy_env = use_proxy_env.split('#')[0].strip()
        proxy_url_env = proxy_url_env.split('#')[0].strip()
        
        logger.info(f"环境变量读取: USE_OPENAI_PROXY={use_proxy_env}, OPENAI_PROXY_URL={proxy_url_env}")
        
        use_proxy = use_proxy_env.lower() == "true"
        logger.info(f"代理配置: use_proxy={use_proxy}")
        
        if use_proxy:
            # 使用代理地址
            self.base_url = proxy_url_env
            logger.info(f"使用代理模式，base_url: {self.base_url}")
        else:
            # 使用官方地址，确保包含完整路径
            self.base_url = "https://api.openai.com/v1"
            logger.info(f"使用官方模式，base_url: {self.base_url}")
        
        # 初始化客户端
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        logger.info(f"OpenAI客户端初始化完成，最终使用地址: {self.base_url}")
    
    def _get_default_analysis(self, reason: str = "Processing failed") -> Dict[str, Any]:
        """返回默认的分析结果，用于错误处理"""
        return {
            "is_trading_related": False,
            "priority": 1,
            "keywords": [],
            "category": "Other",
            "urgency": "Low",
            "sentiment": "Neutral",
            "confidence": 0.0,
            "summary": reason,
            "error": reason
        }
    
    async def analyze_message(self, message_content: str, context_messages: List[str] = None, 
                       attachments: List[Dict[str, Any]] = None, referenced_content: str = None) -> Dict[str, Any]:
        """
        使用GPT-4o分析单条消息，支持图片和引用内容
        
        Args:
            message_content: 要分析的消息内容
            context_messages: 上下文消息列表
            attachments: 附件列表，包含图片URL等信息
            referenced_content: 引用的消息内容
            
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
            system_prompt = """You are a professional cryptocurrency trading message analyst. Your task is to analyze KOL messages, determine if they are trading-related, and extract key information.

Please return the JSON result in the following format:
{
    "is_trading_related": true/false,
    "priority": integer from 1-5,
    "keywords": ["keyword1", "keyword2"],
    "category": "Trading Signal/Market Analysis/Casual Chat/Other",
    "urgency": "Low/Medium/High",
    "sentiment": "Bullish/Bearish/Neutral",
    "confidence": confidence level from 0.0-1.0,
    "summary": "brief message summary"
}

Judgment criteria:
1. Trading-related: Contains cryptocurrency names, prices, technical indicators, buy/sell recommendations, market analysis, etc.
2. Priority: 5=immediate buy/sell signal, 4=important analysis, 3=general information, 2=reference information, 1=casual chat
3. Urgency: Based on time sensitivity and importance
4. Sentiment: Based on market outlook

If images are included, analyze their content for charts, screenshots of trading platforms, price movements, or other trading-related information."""

            # 构建用户消息
            user_message = f"Analyze the following message:\n\n{message_content}"
            
            # 添加引用内容
            if referenced_content:
                user_message += f"\n\nReferenced message:\n{referenced_content}"
            
            # 如果有上下文，添加上下文信息
            if context_messages:
                context_text = "\n".join(context_messages[-3:])  # 只取最近3条
                user_message += f"\n\nContext messages:\n{context_text}"
            
            logger.info(f"正在调用OpenAI API: {self.base_url}")
            logger.debug(f"使用API Key: {self.api_key[:10]}...")  # 只显示前10个字符
            
            # 准备基础消息列表
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            # 检查是否有图片附件 - 改进检测逻辑
            def is_image_attachment(att):
                # 检查 content_type
                content_type = att.get('content_type', '')
                if content_type.startswith('image/'):
                    return True
                
                # 检查文件扩展名
                url = att.get('url', '')
                if url:
                    url_lower = url.lower()
                    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']
                    if any(url_lower.endswith(ext) for ext in image_extensions):
                        return True
                
                # 检查文件名
                filename = att.get('filename', '')
                if filename:
                    filename_lower = filename.lower()
                    if any(filename_lower.endswith(ext) for ext in image_extensions):
                        return True
                
                return False
            
            has_images = attachments and any(is_image_attachment(att) for att in attachments)
            
            # 如果有图片附件，尝试使用多模态消息
            multimodal_messages = None
            if has_images:
                # 创建新的多模态消息列表
                multimodal_messages = [{"role": "system", "content": system_prompt}]
                
                # 构建包含图片的用户消息
                user_content = []
                
                # 添加文本内容
                user_content.append({"type": "text", "text": user_message})
                
                # 添加图片内容
                image_count = 0
                for att in attachments:
                    if is_image_attachment(att):
                        # 优先使用base64编码的data URL（如果存在）
                        image_url = att.get('url')
                        if image_url:
                            # 检查是否已经是data URL格式
                            if image_url.startswith('data:'):
                                # 已经是base64 data URL，直接使用
                                full_url = image_url
                                logger.info(f"使用base64 data URL: {image_url[:50]}...")
                            else:
                                # 如果不是data URL，尝试从附件数据构建base64 URL
                                file_data = att.get('file_data')
                                content_type = att.get('content_type', 'image/png')
                                
                                if file_data:
                                    import base64
                                    try:
                                        # 如果file_data是bytes，直接编码
                                        if isinstance(file_data, bytes):
                                            base64_data = base64.b64encode(file_data).decode('utf-8')
                                        else:
                                            # 如果是其他格式，先转换为bytes
                                            base64_data = base64.b64encode(str(file_data).encode('utf-8')).decode('utf-8')
                                        
                                        full_url = f"data:{content_type};base64,{base64_data}"
                                        logger.info(f"从file_data构建base64 URL，大小: {len(base64_data)} 字符")
                                    except Exception as e:
                                        logger.error(f"构建base64 URL失败: {str(e)}")
                                        continue
                                else:
                                    # 如果没有file_data，跳过这个附件（避免使用无法访问的localhost URL）
                                    logger.warning(f"附件 {att.get('filename', 'unknown')} 没有file_data，跳过")
                                    continue
                            
                            user_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": full_url,
                                    "detail": "low"  # 添加detail参数以控制处理精度
                                }
                            })
                            image_count += 1
                            logger.info(f"添加图片到分析: {att.get('filename', 'unknown')}")
                
                # 将多模态内容添加到消息列表
                multimodal_messages.append({"role": "user", "content": user_content})
                logger.info(f"准备使用多模态消息进行分析，包含 {image_count} 张图片")
            
            # 调用API - 首先尝试使用多模态消息
            response = None
            result = None
            
            # 如果有图片，先尝试多模态请求
            if has_images and multimodal_messages:
                try:
                    logger.info("尝试使用多模态消息调用API")
                    response = self.client.chat.completions.create(
                        model="gpt-4o",  # 使用 gpt-4o 模型
                        messages=multimodal_messages,
                        temperature=0.3,
                        max_tokens=500,
                        response_format={"type": "json_object"}
                    )
                    
                    # 处理响应
                    if hasattr(response, 'choices') and response.choices:
                        result = response.choices[0].message.content
                        logger.info("多模态请求成功")
                    else:
                        logger.warning("多模态请求返回了意外的响应格式")
                        return self._get_default_analysis("多模态请求返回了意外的响应格式")
                        
                except Exception as e:
                    logger.error(f"多模态请求失败: {str(e)}")
                    return self._get_default_analysis(f"多模态请求失败: {str(e)}")
            
            # 如果没有图片，使用普通文本请求
            elif not has_images:
                try:
                    logger.info("使用纯文本消息调用API")
                    response = self.client.chat.completions.create(
                        model="gpt-4o",  # 使用 gpt-4o 模型
                        messages=messages,
                        temperature=0.3,
                        max_tokens=500,
                        response_format={"type": "json_object"}
                    )
                    
                    # 处理不同格式的响应
                    if hasattr(response, 'choices') and response.choices:
                        result = response.choices[0].message.content
                        logger.info("纯文本请求成功")
                    elif isinstance(response, str):
                        result = response
                    elif hasattr(response, 'content'):
                        result = response.content
                    else:
                        logger.error(f"未知的响应格式: {type(response)}, 内容: {response}")
                        return self._get_default_analysis(f"未知的响应格式: {type(response)}")
                        
                except Exception as e:
                    logger.error(f"纯文本请求失败: {str(e)}")
                    return self._get_default_analysis(f"纯文本请求失败: {str(e)}")
            
            # 如果有图片但多模态请求失败，直接返回错误
            else:
                return self._get_default_analysis("包含图片的消息无法处理，多模态请求不可用")
            
            # 检查响应内容是否为空
            if not result or result.strip() == "":
                logger.error("API返回了空响应")
                return self._get_default_analysis("API返回了空响应")
            
            # 检查是否返回了HTML页面（说明API配置有问题）
            if result.strip().lower().startswith('<!doctype html>') or result.strip().lower().startswith('<html'):
                logger.error("API返回了HTML页面而不是JSON，可能的原因：")
                logger.error("1. API Key无效或未配置")
                logger.error("2. 代理服务配置错误")
                logger.error("3. 请求端点路径不正确")
                logger.error(f"当前使用的base_url: {self.base_url}")
                logger.error(f"当前使用的API Key前缀: {self.api_key[:20]}...")
                
                # 返回默认分析而不是抛出异常
                return self._get_default_analysis("API configuration error: HTML page returned")
            
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
                            return self._get_default_analysis("JSON parsing failed")
                    else:
                        logger.error("未能在响应中找到JSON对象")
                        return self._get_default_analysis("JSON object not found")
                else:
                    logger.error("响应内容为空")
                    return self._get_default_analysis("Empty response")
            
            # 如果有图片，在分析结果中标记
            if has_images:
                analysis["contains_images"] = True
                
            logger.info(f"消息分析完成: 交易相关={analysis.get('is_trading_related')}, 优先级={analysis.get('priority')}")
            return analysis
            
        except Exception as e:
            logger.error(f"OpenAI消息分析失败: {str(e)}")
            # 返回默认分析结果
            return self._get_default_analysis(f"Analysis failed: {str(e)}")
    
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
            system_prompt = """You are a trading signal extraction expert. Extract specific trading signal information from KOL messages.

Return JSON format:
{
    "has_signal": true/false,
    "signal_type": "Buy/Sell/Hold/Watch",
    "symbols": ["BTC", "ETH"],
    "target_price": "target price or null",
    "stop_loss": "stop loss price or null", 
    "entry_price": "entry price or null",
    "time_frame": "time period",
    "reasoning": "trading rationale",
    "risk_level": "Low/Medium/High"
}"""

            response = self.client.chat.completions.create(
                model="gpt-4o",  # 使用 gpt-4o 模型
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract trading signals from the following message:\n{message_content}"}
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
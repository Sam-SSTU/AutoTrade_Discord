import os
import aiohttp
import logging
from datetime import datetime
import hashlib
from typing import Optional

message_logger = logging.getLogger("Message Logs")

class FileHandler:
    def __init__(self):
        # 创建存储目录
        self.base_dir = os.path.join(os.getcwd(), 'storage', 'attachments')
        os.makedirs(self.base_dir, exist_ok=True)
        
    async def download_and_save_file(self, url: str, filename: Optional[str] = None) -> Optional[str]:
        """
        下载文件并保存到本地
        返回本地存储路径（相对于storage目录）
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        message_logger.error(f"下载文件失败: {url}, 状态码: {response.status}")
                        return None
                    
                    # 读取文件内容
                    content = await response.read()
                    
                    # 生成文件名
                    if not filename:
                        # 使用URL和时间戳生成唯一文件名
                        hash_base = f"{url}{datetime.now().timestamp()}"
                        filename = hashlib.md5(hash_base.encode()).hexdigest()
                        
                        # 从Content-Type获取文件扩展名
                        content_type = response.headers.get('Content-Type', '')
                        if 'image' in content_type:
                            ext = content_type.split('/')[-1]
                            filename = f"{filename}.{ext}"
                        else:
                            # 从URL获取扩展名
                            ext = os.path.splitext(url)[-1]
                            if ext:
                                filename = f"{filename}{ext}"
                    
                    # 按年月组织文件夹
                    today = datetime.now()
                    year_month = today.strftime('%Y%m')
                    save_dir = os.path.join(self.base_dir, year_month)
                    os.makedirs(save_dir, exist_ok=True)
                    
                    # 保存文件
                    file_path = os.path.join(save_dir, filename)
                    with open(file_path, 'wb') as f:
                        f.write(content)
                    
                    # 返回相对路径
                    return os.path.join('attachments', year_month, filename)
                    
        except Exception as e:
            message_logger.error(f"保存文件出错: {str(e)}")
            return None
            
    def get_file_url(self, relative_path: str) -> str:
        """
        将相对路径转换为可访问的URL
        """
        if not relative_path:
            return ''
        return f"/storage/{relative_path}" 
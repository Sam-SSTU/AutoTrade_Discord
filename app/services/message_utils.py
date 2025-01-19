from typing import Dict, Any

def extract_message_content(message_data: Dict[str, Any]) -> str:
    """提取消息内容，包括文本、附件、嵌入内容等"""
    content_parts = []
    
    # 1. 处理基本文本内容
    if message_data.get("content"):
        content_parts.append(message_data["content"])
    
    # 2. 处理附件
    attachments = message_data.get("attachments", [])
    if attachments:
        for attachment in attachments:
            url = attachment.get('url', '')
            filename = attachment.get('filename', '')
            content_parts.append(f"[附件] {filename} - {url}")
            
            # 如果是图片，添加图片描述
            if attachment.get('content_type', '').startswith('image/'):
                content_parts.append(f"[图片] {url}")
            # 如果是视频
            elif attachment.get('content_type', '').startswith('video/'):
                content_parts.append(f"[视频] {url}")
    
    # 3. 处理嵌入内容
    embeds = message_data.get("embeds", [])
    if embeds:
        for embed in embeds:
            embed_parts = []
            if embed.get("title"):
                embed_parts.append(f"标题: {embed['title']}")
            if embed.get("description"):
                embed_parts.append(embed["description"])
            if embed.get("fields"):
                for field in embed["fields"]:
                    embed_parts.append(f"{field.get('name', '')}: {field.get('value', '')}")
            if embed.get("image"):
                embed_parts.append(f"[嵌入图片] {embed['image'].get('url', '')}")
            if embed.get("thumbnail"):
                embed_parts.append(f"[缩略图] {embed['thumbnail'].get('url', '')}")
            if embed.get("video"):
                embed_parts.append(f"[嵌入视频] {embed['video'].get('url', '')}")
            if embed_parts:
                content_parts.append("[嵌入内容]\n" + "\n".join(embed_parts))
    
    # 4. 处理引用消息
    referenced_message = message_data.get("referenced_message")
    if referenced_message:
        ref_content = referenced_message.get("content", "")
        ref_author = referenced_message.get("author", {}).get("username", "Unknown")
        content_parts.append(f"[引用 {ref_author}]\n{ref_content}")
    
    # 5. 处理特殊消息类型
    message_type = message_data.get("type", 0)
    if message_type != 0:  # 不是普通消息
        type_descriptions = {
            1: "成员加入",
            2: "成员提升",
            3: "频道置顶",
            4: "频道关注",
            5: "频道消息置顶",
            6: "频道消息取消置顶",
            7: "欢迎消息",
            8: "频道提升",
            9: "回复",
            10: "应用命令",
            11: "线程创建",
            12: "线程删除",
            13: "线程更新",
            14: "频道归档",
            15: "频道取消归档",
            16: "线程归档",
            17: "线程取消归档"
        }
        content_parts.append(f"[{type_descriptions.get(message_type, '未知类型消息')}]")
    
    # 6. 处理组件（按钮、下拉菜单等）
    components = message_data.get("components", [])
    if components:
        for component in components:
            if component.get("type") == 1:  # Action Row
                for child in component.get("components", []):
                    comp_type = child.get("type")
                    if comp_type == 2:  # Button
                        content_parts.append(f"[按钮] {child.get('label', '未命名按钮')}")
                    elif comp_type == 3:  # Select Menu
                        content_parts.append("[下拉菜单]")
    
    # 7. 处理Sticker贴纸
    stickers = message_data.get("sticker_items", [])
    if stickers:
        for sticker in stickers:
            content_parts.append(f"[贴纸] {sticker.get('name', '未知贴纸')}")
    
    # 8. 处理反应表情
    reactions = message_data.get("reactions", [])
    if reactions:
        reaction_parts = []
        for reaction in reactions:
            emoji = reaction.get("emoji", {})
            name = emoji.get("name", "")
            count = reaction.get("count", 0)
            reaction_parts.append(f"{name}: {count}")
        if reaction_parts:
            content_parts.append("[表情回应] " + ", ".join(reaction_parts))
    
    # 如果没有任何内容，检查是否有其他类型的内容
    if not content_parts:
        # 检查是否有任何类型的媒体内容
        if message_data.get("attachments") or message_data.get("embeds") or message_data.get("sticker_items"):
            content_parts.append("[媒体消息]")
        else:
            content_parts.append("[空消息]")
    
    return "\n".join(content_parts) 
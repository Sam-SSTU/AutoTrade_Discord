# 量化与KOL消息源的虚拟币交易系统

基于Python的自动化虚拟币交易系统，结合社交媒体KOL消息分析和量化交易策略，实现智能化交易决策。系统从Discord频道捕获消息，将其存储在数据库中，并提供Web界面来查看和管理这些消息。

**注意：** 目前币安集成组件和AI分析组件仍在开发中。

## 🌟 核心功能

### 社交媒体监控
- Discord频道和论坛帖子实时监控
- 消息历史记录和同步
- 未读消息追踪
- 附件和嵌入内容支持

### 消息分析（开发中）
- KOL消息智能分类
- 交易信号提取
- 市场情绪分析
- 多维度数据整合

### 交易执行系统（开发中）
- 币安API集成
- 自动化交易执行
- 风险控制管理
- 订单跟踪与管理

### 系统监控
- 实时WebSocket连接状态
- 数据库连接监控
- API健康检查
- 消息同步状态监控

## 🛠️ 技术架构

### 后端技术栈
- **Web框架**: FastAPI v0.104.1
- **ASGI服务器**: Uvicorn v0.24.0
- **数据库**: PostgreSQL 12+
- **ORM**: SQLAlchemy v2.0.23
- **缓存**: Redis v5.0.1
- **Discord SDK**: discord.py v2.3.2

### 前端技术栈
- **框架**: Vue.js v2.6.14
- **UI组件**: Element UI
- **样式**: Bootstrap v5.1.3
- **HTTP客户端**: Axios

## 📋 系统要求

- Python 3.8+
- PostgreSQL 12+
- Redis 6+
- Node.js 14+

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone [your-repository-url]
cd AutoTrade_Discord

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate  # Windows
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置文件

创建 `.env` 文件并配置以下参数：
```env
# 数据库配置
DATABASE_URL=postgresql://user:password@localhost/dbname

# Discord配置
DISCORD_USER_TOKEN=your_discord_token

# Redis配置
REDIS_URL=redis://localhost:6379

# Telegram日志配置（可选）
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 4. 初始化数据库

```bash
# 运行数据库迁移
alembic upgrade head

# 重置数据库（如需要）
python reset_db.py
```

### 5. 启动服务

```bash
# 启动主服务
uvicorn app.main:app --reload

# 停止服务（如需要）
kill -9 $(lsof -ti:8000)
```

## 📊 系统功能

### Discord消息管理
1. 频道管理
   - 同步频道列表
   - 激活/停用频道
   - 论坛帖子同步
   - 频道分类管理

2. 消息监控
   - 实时消息捕获
   - 历史消息同步
   - 附件处理
   - 未读消息追踪

3. 开发者工具
   - 系统日志查看
   - 消息日志查看
   - 数据库操作
   - WebSocket状态监控

## 🔒 安全建议

1. API安全
   - Discord Token安全存储
   - 环境变量管理
   - API访问控制

2. 数据安全
   - 数据库备份
   - 敏感信息加密
   - 访问权限控制

3. 系统安全
   - 依赖包更新
   - 日志审计
   - 错误处理

## 📁 项目结构

```
/
├── alembic/           # 数据库迁移脚本
├── app/               # 主应用程序代码
│   ├── ai/           # AI组件（开发中）
│   ├── api/          # API端点
│   ├── binance/      # 币安集成（开发中）
│   ├── config/       # 应用程序配置
│   ├── models/       # 数据库模型
│   ├── services/     # 业务逻辑服务
│   ├── static/       # 静态资源
│   ├── templates/    # HTML模板
│   └── utils/        # 工具函数
├── data/             # 数据存储
├── docs/             # 文档
├── examples/         # 示例代码
└── storage/          # 文件存储
```

## 📈 开发计划

1. AI组件实现
   - 消息分析系统
   - 交易信号提取
   - 市场情绪分析

2. 币安集成
   - API连接实现
   - 交易执行系统
   - 风险控制模块

3. 系统优化
   - 错误处理增强
   - 日志系统完善
   - 性能优化

## 📄 许可证

MIT License

emoji from: https://favicon.io/emoji-favicons/thinking-face

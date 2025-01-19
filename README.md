# Discord Message Manager

一个用于监控和管理Discord频道消息的Web应用程序。支持消息存储、黑名单管理、消息查询和过滤等功能。

## 功能特点

- 自动监控指定Discord频道的消息
- 将消息存储到数据库中，支持引用消息的关联存储
- 基于权限错误的自动频道黑名单管理
- Web界面支持:
  - 消息查询和过滤(按频道ID、作者名称、消息类型等)
  - 消息删除
  - 黑名单管理(添加/删除频道)
  - 分页显示消息列表

## 项目结构

```
app/
├── api/
│   └── messages.py          # API路由处理(消息和黑名单相关接口)
├── config/
│   ├── author_categories.py # 作者分类配置
│   ├── blacklist.py        # 黑名单配置
│   └── discord_config.py   # Discord相关配置
├── models/
│   └── base.py            # 数据库模型定义(KOL和Message)
├── services/
│   ├── discord_client.py  # Discord API客户端实现
│   └── message_handler.py # 消息处理服务
├── static/                # 静态资源文件
├── templates/
│   └── index.html        # Web界面模板
├── database.py           # 数据库连接配置
└── main.py              # FastAPI应用入口

```

## 配置说明

1. 创建并配置 `.env` 文件:

```env
# Discord Configuration
DISCORD_USER_TOKEN=your_discord_token
DISCORD_CHANNEL_IDS=channel_id1,channel_id2

# Database Configuration
DATABASE_URL=postgresql://username:password@localhost:5432/dbname
```

2. 安装依赖:

```bash
pip install -r requirements.txt
```

## 启动说明

1. 确保PostgreSQL数据库已启动并创建了相应的数据库

2. 启动应用:

```bash
uvicorn app.main:app --reload --port 8001
```

3. 访问Web界面:
   - 打开浏览器访问 `http://localhost:8001`
   - API文档访问 `http://localhost:8001/docs`

## API接口

### 消息相关

- `GET /api/messages` - 获取消息列表，支持过滤和分页
- `DELETE /api/messages/{message_id}` - 删除指定消息

### 黑名单相关

- `GET /api/blacklist` - 获取黑名单列表
- `POST /api/blacklist/{channel_id}` - 添加频道到黑名单
- `DELETE /api/blacklist/{channel_id}` - 从黑名单中移除频道

## 注意事项

1. Discord Token权限要求:
   - 需要有读取消息的权限
   - 需要有访问频道的权限

2. 数据库注意事项:
   - 首次启动会自动创建必要的数据表
   - 建议定期备份数据库

3. 黑名单机制:
   - 频道在连续3次出现权限错误后会被自动加入黑名单
   - 可以通过Web界面手动管理黑名单

## 开发说明

- 使用FastAPI框架开发
- 使用SQLAlchemy进行数据库操作
- 前端使用Vue.js + Bootstrap构建
- 支持热重载，便于开发调试 
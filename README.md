# Discord Message Manager
## Current version: 0.0.1
## Currently focusing on this project since 2025-03-13


一个用于监控和管理 Discord 消息的 Web 应用程序。支持实时消息监听、历史消息同步、频道管理等功能。

## 功能特点

- 实时监控 Discord 消息
- 支持查看和管理多个频道
- 消息历史记录和同步
- 开发者模式，支持更多高级功能
- 支持消息附件和嵌入内容的显示
- 实时日志查看

## 系统要求

- Python 3.8+
- PostgreSQL 12+
- Node.js 14+ (用于前端开发，可选)

## 安装步骤

### 1. 克隆项目

```bash
git clone [your-repository-url]
cd AutoTrade_Discord
```

### 2. 创建虚拟环境

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 设置数据库

1. 安装 PostgreSQL（如果尚未安装）
   - Windows: 从 [PostgreSQL 官网](https://www.postgresql.org/download/windows/) 下载安装包
   - macOS: 使用 Homebrew 安装
     ```bash
     brew install postgresql
     ```
   - Linux:
     ```bash
     sudo apt-get update
     sudo apt-get install postgresql postgresql-contrib
     ```

2. 创建数据库和用户
   ```sql
   CREATE DATABASE discord_manager;
   CREATE USER discord_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE discord_manager TO discord_user;
   ```

3. 配置数据库连接
   创建 `.env` 文件并添加以下内容：
   ```
   DATABASE_URL=postgresql://discord_user:your_password@localhost/discord_manager
   DISCORD_USER_TOKEN=your_discord_token
   ```

4. 初始化数据库
   ```bash
   # 运行数据库迁移
   alembic upgrade head
   ```

### 5. 获取 Discord Token

1. 打开 Discord Web 版
2. 按 F12 打开开发者工具
3. 在 Network 标签页中找到任意请求
4. 在请求头中找到 `Authorization` 字段的值
5. 将该值添加到 `.env` 文件的 `DISCORD_USER_TOKEN` 中

### 6. 运行应用

```bash
# 启动应用
uvicorn app.main:app --reload


```
stop
kill -9 $(lsof -ti:8000)

refresh database
python reset_db.py

访问 http://localhost:8000 即可打开应用。

## 使用说明

### 基本功能

1. 频道管理
   - 点击"同步频道列表"更新可访问的频道
   - 使用搜索框快速查找频道
   - 灰色显示的频道表示无访问权限

2. 消息查看
   - 点击频道查看消息历史
   - 支持无限滚动加载更多消息
   - 支持查看消息附件和嵌入内容

### 开发者模式

点击右上角的"开发者模式"按钮启用以下功能：

1. 历史消息同步
   - 输入要同步的消息数量
   - 点击"Sync"开始同步

2. 数据库操作
   - 使用"Clear All Messages"清空数据库

3. 日志查看
   - System Logs: 显示系统运行日志
   - Message Logs: 显示消息相关的日志

## 常见问题

1. 数据库连接错误
   - 检查 PostgreSQL 服务是否正在运行
   - 验证数据库连接字符串是否正确
   - 确认数据库用户权限是否正确

2. Discord Token 无效
   - 确保 token 未过期
   - 验证 token 格式是否正确
   - 检查是否有必要的 Discord 权限

3. 消息不显示
   - 检查频道权限设置
   - 确认 WebSocket 连接状态
   - 查看浏览器控制台是否有错误信息

## 开发说明

### 项目结构

```
app/
├── api/            # API 路由
├── models/         # 数据库模型
├── services/       # 业务逻辑
├── templates/      # 前端模板
└── main.py         # 应用入口

alembic/           # 数据库迁移
requirements.txt   # Python 依赖
```
 
### 数据库迁移

添加新的数据库变更：
```bash
alembic revision -m "description"
```

应用迁移：
```bash
alembic upgrade head
```

回滚迁移：
```bash
alembic downgrade -1
```

## 安全注意事项

1. 请勿泄露你的 Discord Token
2. 定期更新依赖包以修复安全漏洞
3. 在生产环境中使用更安全的配置

## 许可证

[Your License] 
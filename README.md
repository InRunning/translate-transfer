# Translate Transfer - 大模型请求转发服务

一个基于 Flask 的大模型请求转发服务，主要用于翻译功能，支持单词和句子的智能翻译，并支持流式响应。

## 🚀 功能特性

- **智能翻译识别**：自动识别输入是单词还是句子，使用不同的翻译策略
- **流式响应支持**：支持流式和非流式两种响应模式
- **智能缓存机制**：单词翻译结果自动缓存，提升响应速度，减少API调用
- **灵活配置**：支持通过配置文件和环境变量进行配置
- **代理转发**：将请求转发到华为云 DeepSeek API
- **健康检查**：提供健康检查端点
- **错误处理**：完善的错误处理和响应机制

## 📋 系统要求

- Python 3.x
- 虚拟环境支持 (venv)
- 网络连接（用于调用外部 API）

## 🛠️ 安装步骤

### 1. 克隆项目
```bash
git clone <repository-url>
cd translate-transfer
```

### 2. 创建虚拟环境
```bash
python3 -m venv venv
```

### 3. 激活虚拟环境
```bash
# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 4. 安装依赖
```bash
pip install -r requirements.txt
```

### 5. 配置 API 密钥
创建 `local.yaml` 文件并配置 API 密钥：

```yaml
Relay:
  Model: "DeepSeek-V3"
  Url: "https://api.modelarts-maas.com/v1/chat/completions"
  ApiKey: "your-api-key-here"
  Temperature: 0
  Stream: True
  Cache: True

# 单词缓存数据库配置（默认 SQLite）
Database:
  # mysql / sqlite / postgresql
  Type: "sqlite"
  Sqlite:
    Path: "word_cache.db"
```

或者设置环境变量：
```bash
export DEEPSEEK_API_KEY="your-api-key-here"
```

## 🚀 启动服务

### 使用启动脚本（推荐）
```bash
chmod +x start.sh
./start.sh
```

### 直接启动
```bash
python3 app.py
```

服务将在 `http://localhost:10283` 启动。

## 📡 API 端点

### 1. 翻译代理端点
- **路径**: `/zotero`
- **方法**: `POST`
- **描述**: 主要的翻译服务端点，自动识别单词/句子并调用相应的翻译策略

**请求示例**：
```bash
curl -X POST http://127.0.0.1:10283/zotero \
  -H "Content-Type: application/json" \
  -d '{
    "model": "DeepSeek-V3",
    "messages": [
      {"role": "user", "content": "example"}
    ],
    "temperature": 0,
    "stream": true
  }'
```

**响应示例**（单词翻译）：
```json
{
  "model": "DeepSeek-V3",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "例子\n美式音标：/ɪɡˈzæmpəl/, 英式音标：/ɪɡˈzɑːmpəl/"
      }
    }
  ]
}
```

### 2. 健康检查端点
- **路径**: `/health`
- **方法**: `GET`
- **描述**: 检查服务运行状态

**请求示例**：
```bash
curl http://127.0.0.1:10283/health
```

**响应示例**：
```json
{
  "status": "healthy"
}
```

### 3. 服务信息端点
- **路径**: `/`
- **方法**: `GET`
- **描述**: 获取服务基本信息

**请求示例**：
```bash
curl http://127.0.0.1:10283/
```

**响应示例**：
```json
{
  "message": "翻译服务",
  "version": "1.0.0",
  "endpoints": {
    "zotero": "/zotero",
    "health": "/health",
    "index": "/"
  }
}
```

## 🔧 配置说明

### 配置文件结构

#### config.json
```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 10283,
    "debug": true,
    "threaded": true
  },
  "routes": {
    "zotero": "/zotero",
    "health": "/health",
    "index": "/"
  }
}
```

#### local.yaml
```yaml
Relay:
  Model: "DeepSeek-V3"           # 使用的模型
  Url: "https://api.modelarts-maas.com/v1/chat/completions"  # API 地址
  ApiKey: "your-api-key"         # API 密钥
  Temperature: 0                 # 温度参数
  Stream: true                   # 是否启用流式响应
  Cache: true                    # 是否启用单词翻译缓存

Database:
  # 选择：mysql / sqlite / postgresql
  Type: "sqlite"

  # SQLite 配置（Type=sqlite 时使用）
  Sqlite:
    Path: "word_cache.db"

  # MySQL 配置（Type=mysql 时使用）
  Mysql:
    Host: "127.0.0.1"
    Port: 3306
    Dbname: "translate_transfer"
    Username: "root"
    Password: ""
    Params: "charset=utf8mb4"

  # PostgreSQL 配置（Type=postgresql 时使用）
  Postgresql:
    Host: "127.0.0.1"
    Port: 5432
    Dbname: "translate_transfer"
    Username: "postgres"
    Password: ""
    Params: "sslmode=disable"
```

### 环境变量

- `DEEPSEEK_API_KEY`: 华为云 DeepSeek API 密钥
- `FLASK_ENV`: Flask 运行环境（development/production）

## 🧪 测试

### 运行测试脚本
```bash
python3 test_app.py
```

测试脚本会自动测试所有端点：
- 健康检查端点
- 服务信息端点
- Zotero 代理端点
- 错误处理

### 手动测试
```bash
# 测试健康检查
curl http://localhost:10283/health

# 测试翻译功能
curl -X POST http://localhost:10283/zotero \
  -H "Content-Type: application/json" \
  -d '{"model": "DeepSeek-V3", "messages": [{"role": "user", "content": "Hello"}], "temperature": 0, "stream": false}'
```

### 4. 缓存机制
服务内置了智能缓存机制，专门针对单词翻译进行优化：

- **自动缓存**：单词翻译结果会自动存储到配置的数据库中（默认 SQLite）
- **缓存命中**：相同单词的后续请求直接从缓存返回，无需调用上游 API
- **流式缓存**：支持流式响应的缓存，模拟真实的流式输出体验
- **缓存配置**：可通过 `Cache` 参数启用或禁用缓存功能

**数据库支持**：
- SQLite / MySQL / PostgreSQL 均可（通过 `local.yaml` 的 `Database.Type` 切换）
- 使用 MySQL 或 PostgreSQL 时，请确保目标数据库已创建且安装了对应驱动（例如 PostgreSQL 常用 `psycopg2`/`psycopg`）

**缓存配置示例**：
```yaml
Relay:
  Cache: true  # 启用缓存（默认为 true）
```

**缓存优势**：
- 🚀 **响应更快**：缓存命中时响应时间显著缩短
- 💰 **节省成本**：减少上游 API 调用，降低使用成本
- 🔄 **稳定性**：即使上游 API 不可用，缓存内容仍可提供服务

## 📚 使用场景

### 1. 单词翻译
服务会自动识别单词输入，提供：
- 最常用的释义
- 美式音标
- 英式音标

**输入**: `example`
**输出**: 
```
例子
美式音标：/ɪɡˈzæmpəl/, 英式音标：/ɪɡˈzɑːmpəl/
```

### 2. 句子翻译
服务会自动识别句子输入，提供：
- 句子的完整释义

**输入**: `I want to go home`
**输出**: `我想回家`

### 3. 流式响应
支持实时流式翻译，适用于需要即时反馈的场景。

## 🛡️ 错误处理

服务包含完善的错误处理机制：

- **400 Bad Request**: 请求格式错误或缺少必要参数
- **500 Internal Server Error**: 服务器内部错误或上游 API 调用失败
- **网络错误**: 自动处理网络连接问题

## 📝 开发文档

### 项目结构
```
translate-transfer/
├── app.py                 # 主应用文件
├── config.json           # 基础配置文件
├── local.example.yaml    # API 配置示例
├── requirements.txt      # Python 依赖
├── start.sh             # 启动脚本
├── test_app.py          # 测试脚本
├── README.md            # 项目说明
└── docs/                # 文档目录
    ├── 实现文档.md
    ├── 依赖文档.md
    ├── 请求.md
    └── func/
        └── zotero_proxy.md
```

### 核心功能说明

#### 1. 智能识别
[`is_word()`](app.py:31) 函数使用正则表达式判断输入是否为单词：
```python
def is_word(text):
    return bool(re.match(r'^[a-zA-Z]{1,50}$', text.strip()))
```

#### 2. 负载构建
[`build_outgoing_payload()`](app.py:35) 函数根据输入类型构建不同的系统提示词：
- 单词：包含释义和音标信息
- 句子：包含句子翻译信息

#### 3. 代理转发
[`proxy_deepseek()`](app.py:77) 函数负责将请求转发到华为云 DeepSeek API，支持流式和非流式响应。

## 🔧 故障排除

### 常见问题

1. **API 密钥未设置**
   ```
   错误：Authorization header is required
   解决：检查 local.yaml 中的 ApiKey 或设置 DEEPSEEK_API_KEY 环境变量
   ```

2. **端口被占用**
   ```
   错误：Address already in use
   解决：修改 config.json 中的端口号或停止占用端口的进程
   ```

3. **依赖安装失败**
   ```
   解决：尝试更换 pip 源
   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

### 日志查看
启用 debug 模式查看详细日志：
```bash
python3 app.py
```

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📞 联系方式

如有问题或建议，请通过以下方式联系：
- 提交 Issue
- 发送邮件至 [your-email@example.com]

---

**注意**: 本项目仅供学习和研究使用，请遵守相关 API 的使用条款。

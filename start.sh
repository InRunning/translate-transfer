#!/bin/bash

# 大模型请求转发服务启动脚本

echo "激活虚拟环境..."
source venv/bin/activate

echo "检查环境变量..."
if [ -z "$OPENAI_API_KEY" ]; then
    echo "警告: OPENAI_API_KEY 环境变量未设置"
    echo "请设置API密钥: export OPENAI_API_KEY='your-api-key'"
    echo "或者直接修改 app.py 中的 TARGET_MODEL_API_KEY"
fi

echo "启动大模型请求转发服务..."
echo "监听端口: 10283"
echo "路由: /zotero"
echo "按 Ctrl+C 停止服务"
echo ""

# 启动Python应用
python3 app.py
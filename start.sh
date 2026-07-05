#!/bin/bash

# 大模型请求转发服务启动脚本

PORT=$(sed -n 's/.*"port"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' config.json | head -1)
if [ -z "$PORT" ]; then
    PORT=13234
fi

echo "检查环境变量..."
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "提示: DEEPSEEK_API_KEY 环境变量未设置，将优先使用 local.yaml 中的 Relay.ApiKey"
fi

echo "启动大模型请求转发服务..."
echo "监听端口: $PORT"
echo "路由: /zotero"
echo "按 Ctrl+C 停止服务"
echo ""

# 启动 Go 应用
go run .

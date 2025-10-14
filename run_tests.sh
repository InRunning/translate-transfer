#!/bin/bash

# Flask应用测试启动脚本
# 用于启动Flask应用并运行测试

echo "🚀 Flask应用测试脚本"
echo "===================="

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装，请先安装Python3"
    exit 1
fi

# 检查requests库是否安装
if ! python3 -c "import requests" &> /dev/null; then
    echo "⚠️  requests库未安装，正在安装..."
    pip3 install requests
fi

# 设置环境变量（可选）
export FLASK_APP=app.py
export FLASK_ENV=development

# 检查是否提供了OPENAI_API_KEY
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY环境变量未设置"
    echo "💡 可以设置环境变量来测试真实的API调用"
    echo "   export OPENAI_API_KEY='your-api-key-here'"
    echo ""
fi

echo "📋 测试选项:"
echo "1. 启动Flask应用并运行测试"
echo "2. 仅运行测试（假设应用已启动）"
echo "3. 仅启动Flask应用"
echo "4. 仅运行测试脚本"
echo ""

read -p "请选择操作 (1-4): " choice

case $choice in
    1)
        echo "🚀 启动Flask应用并在后台运行..."
        python3 app.py &
        FLASK_PID=$!
        echo "✅ Flask应用已启动 (PID: $FLASK_PID)"
        echo "⏳ 等待应用启动完成..."
        sleep 3
        
        echo "🧪 开始运行测试..."
        python3 test_app.py
        
        echo ""
        read -p "测试完成，是否停止Flask应用? (y/n): " stop_app
        if [[ $stop_app == "y" || $stop_app == "Y" ]]; then
            echo "🛑 停止Flask应用..."
            kill $FLASK_PID
            echo "✅ Flask应用已停止"
        fi
        ;;
    2)
        echo "🧪 开始运行测试..."
        python3 test_app.py
        ;;
    3)
        echo "🚀 启动Flask应用..."
        python3 app.py
        ;;
    4)
        echo "🧪 开始运行测试..."
        python3 test_app.py
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac

echo ""
echo "🎉 测试完成！"
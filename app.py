from flask import Flask, request, jsonify, Response
import requests
import json
import os
from urllib.parse import urljoin
import logging

# 加载配置
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # 如果配置文件不存在，使用默认配置
        return {
            "server": {
                "host": "0.0.0.0",
                "port": 10283,
                "debug": True,
                "threaded": True
            },
            "routes": {
                "zotero": "/zotero",
                "health": "/health",
                "index": "/"
            },
            "target_api": {
                "url": "https://api.openai.com/v1/chat/completions",
                "timeout": 30,
                "headers": {
                    "Content-Type": "application/json"
                }
            }
        }

config = load_config()

app = Flask(__name__)

# 配置参数
PORT = config['server']['port']
ZOTERO_ROUTE = config['routes']['zotero']
TARGET_MODEL_API = config['target_api']['url']
TARGET_MODEL_API_KEY = os.getenv('OPENAI_API_KEY', '')  # 从环境变量获取API密钥

# 配置日志
logging.basicConfig(
    level=getattr(logging, config.get('logging', {}).get('level', 'INFO')),
    format=config.get('logging', {}).get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)
logger = logging.getLogger(__name__)

@app.route(ZOTERO_ROUTE, methods=['POST'])
def zotero_proxy():
    """
    处理/zotero路由的请求转发
    """
    try:
        # 获取请求数据
        request_data = request.get_json()
        if not request_data:
            return jsonify({"error": "Invalid JSON data"}), 400
        
        # 记录请求信息
        logger.info(f"收到请求: {request.method} {request.url}")
        logger.debug(f"请求数据: {json.dumps(request_data, ensure_ascii=False, indent=2)}")
        
        # 构造目标API请求
        target_headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {TARGET_MODEL_API_KEY}' if TARGET_MODEL_API_KEY else ''
        }
        
        # 发送请求到目标大模型API
        timeout = config['target_api']['timeout']
        response = requests.post(
            TARGET_MODEL_API,
            json=request_data,
            headers=target_headers,
            timeout=timeout
        )
        
        # 检查响应状态
        if response.status_code != 200:
            logger.error(f"目标API返回错误: {response.status_code}")
            logger.error(f"错误响应: {response.text}")
            return jsonify({
                "error": f"Target API returned status {response.status_code}",
                "details": response.text
            }), response.status_code
        
        # 获取响应数据
        response_data = response.json()
        
        # 记录响应信息
        logger.debug(f"响应数据: {json.dumps(response_data, ensure_ascii=False, indent=2)}")
        
        return jsonify(response_data)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"请求异常: {str(e)}")
        return jsonify({"error": f"Request failed: {str(e)}"}), 500
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析异常: {str(e)}")
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"未知异常: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """
    健康检查接口
    """
    return jsonify({"status": "healthy", "port": PORT})

@app.route('/', methods=['GET'])
def index():
    """
    首页接口
    """
    return jsonify({
        "message": "大模型请求转发服务",
        "version": "1.0.0",
        "endpoints": {
            "zotero": f"POST {ZOTERO_ROUTE}",
            "health": "GET /health",
            "index": "GET /"
        }
    })

if __name__ == '__main__':
    logger.info("启动大模型请求转发服务...")
    logger.info(f"监听端口: {PORT}")
    logger.info(f"路由: {ZOTERO_ROUTE}")
    logger.info(f"目标API: {TARGET_MODEL_API}")
    logger.info(f"访问地址: http://localhost:{PORT}")
    
    # 启动Flask应用
    app.run(
        host=config['server']['host'],
        port=PORT,
        debug=config['server']['debug'],
        threaded=config['server']['threaded']
    )
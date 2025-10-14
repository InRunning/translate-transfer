from flask import Flask, request, jsonify, Response
import requests
import json
import os
from urllib.parse import urljoin
import logging
import re

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

def is_word(text):
    """检测文本是否为单词"""
    # 只包含字母，长度在1-50个字符之间
    return bool(re.match(r'^[a-zA-Z]{1,50}$', text))

def get_word_translation(word):
    """获取单词翻译（包含音标）"""
    # 这里使用一个简单的字典作为示例
    # 在实际应用中，可以调用词典API或使用更复杂的翻译服务
    word_dict = {
        "hello": {
            "definition": "你好，喂",
            "us_pronunciation": "/həˈloʊ/",
            "uk_pronunciation": "/həˈləʊ/"
        },
        "world": {
            "definition": "世界",
            "us_pronunciation": "/wɜːrld/",
            "uk_pronunciation": "/wɜːld/"
        },
        "python": {
            "definition": "Python编程语言",
            "us_pronunciation": "/ˈpaɪθɑːn/",
            "uk_pronunciation": "/ˈpʌɪθɒn/"
        },
        "computer": {
            "definition": "计算机",
            "us_pronunciation": "/kəmˈpjuːtər/",
            "uk_pronunciation": "/kəmˈpjuːtə/"
        },
        "programming": {
            "definition": "编程",
            "us_pronunciation": "/ˈproʊɡræmɪŋ/",
            "uk_pronunciation": "/ˈprəʊɡræmɪŋ/"
        }
    }
    
    return word_dict.get(word.lower(), {
        "definition": f"单词 '{word}' 的释义",
        "us_pronunciation": "/us/",
        "uk_pronunciation": "/uk/"
    })

def get_general_translation(text):
    """获取非单词文本的翻译"""
    # 这里使用一个简单的示例
    # 在实际应用中，可以调用翻译API
    translations = {
        "hello world": "你好世界",
        "good morning": "早上好",
        "thank you": "谢谢",
        "I love you": "我爱你",
        "how are you": "你好吗"
    }
    
    return translations.get(text.lower(), f"文本 '{text}' 的释义")

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
        
        # 检查是否为单词翻译请求
        if 'messages' in request_data and len(request_data['messages']) > 0:
            user_message = request_data['messages'][-1].get('content', '')
            if isinstance(user_message, str) and user_message.strip():
                # 检查是否为单词
                if is_word(user_message.strip()):
                    # 单词翻译 - 返回释义和音标
                    translation = get_word_translation(user_message.strip())
                    response_data = {
                        "choices": [{
                            "message": {
                                "role": "assistant",
                                "content": f"单词释义：{translation['definition']}\n美式音标：{translation['us_pronunciation']}\n英式音标：{translation['uk_pronunciation']}"
                            }
                        }]
                    }
                    return jsonify(response_data)
                else:
                    # 非单词翻译 - 直接返回释义
                    translation = get_general_translation(user_message.strip())
                    response_data = {
                        "choices": [{
                            "message": {
                                "role": "assistant",
                                "content": translation
                            }
                        }]
                    }
                    return jsonify(response_data)
    

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
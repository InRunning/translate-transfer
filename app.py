from flask import Flask, request, jsonify
import requests
import json
import os
import re

def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "server": {"host": "0.0.0.0", "port": 10283, "debug": True, "threaded": True},
            "routes": {"zotero": "/zotero", "health": "/health", "index": "/"}
        }

config = load_config()
app = Flask(__name__)

def is_word(text):
    """检测是否为单词"""
    return bool(re.match(r'^[a-zA-Z]{1,50}$', text.strip()))

def call_deepseek_api(text, is_word_input):
    """调用DeepSeek API"""
    if is_word_input:
        system_prompt = "你是一个智能翻译助手，下面是单词，你需要给出该单词最常用的一个释义，并给出美式音标和英式音标，示例：输入：example 输出格式: 例子\n 美式音标：/ɪɡˈzæmpəl/, 英式音标：/ɪɡˈzɑːmpəl/ ."
    else:
        system_prompt = "你是一个智能翻译助手，下面是句子，请给出该句子的释义。示例：输入：I want to go home 输出: 我想回家 ."
    
    payload = {
        "model": "DeepSeek-V3",
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY', '')}"
    }
    
    try:
        response = requests.post(
            "https://api.modelarts-maas.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}

@app.route(config['routes']['zotero'], methods=['POST'])
def zotero_proxy():
    try:
        request_data = request.get_json()
        if not request_data or 'messages' not in request_data:
            return jsonify({"error": "Invalid request"}), 400
        
        user_message = request_data['messages'][-1].get('content', '').strip()
        if not user_message:
            return jsonify({"error": "Empty message"}), 400
        
        is_word_input = is_word(user_message)
        result = call_deepseek_api(user_message, is_word_input)
        
        if "error" in result:
            return jsonify({"error": result["error"]}), 500
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"})

@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "翻译服务", "version": "1.0.0"})

if __name__ == '__main__':
    app.run(
        host=config['server']['host'],
        port=config['server']['port'],
        debug=config['server']['debug'],
        threaded=config['server']['threaded']
    )

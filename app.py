from flask import Flask, request, jsonify, Response
from flask import stream_with_context
import requests
import json
import os
import re
import yaml
from typing import Any, Dict, List, Optional

def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "server": {"host": "0.0.0.0", "port": 10283, "debug": True, "threaded": True},
            "routes": {"zotero": "/zotero", "anx_reader": "/anx-reader", "health": "/health", "index": "/"}
        }

def load_api_config():
    try:
        with open('local.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None

config = load_config()
api_config = load_api_config()
app = Flask(__name__)

def is_word(text):
    """检测是否为单词"""
    return bool(re.match(r'^[a-zA-Z]{1,50}$', text.strip()))

def build_outgoing_payload(incoming: Dict[str, Any], is_word_input: bool) -> Dict[str, Any]:
    """基于入参构造转发给大模型的payload，并按词/句插入不同的system prompt。

    - 尽量透传原始字段，仅覆盖必要字段（model/stream/messages/temperature默认）。
    - messages 最前插入我们自定义的 system 提示词，其余保持入参顺序不变。
    """
    # 选择词/句不同的 system prompt
    if is_word_input:
        system_prompt = (
            "你是一个智能翻译助手，下面是单词，你需要给出该单词最常用的一个释义，"
            "并给出美式音标和英式音标，示例：输入：example 输出格式: 例子\n 美式音标：/ɪɡˈzæmpəl/, 英式音标：/ɪɡˈzɑːmpəl/ ."
        )
    else:
        system_prompt = (
            "你是一个智能翻译助手，下面是句子，请给出该句子的释义。"
            "示例：输入：I want to go home 输出: 我想回家 ."
        )

    outgoing = dict(incoming)  # 透传基础字段

    # 覆盖/补全必要字段
    model = incoming.get('model') or (api_config and api_config.get('Relay', {}).get('Model')) or "DeepSeek-V3"
    stream = incoming.get('stream') if incoming.get('stream') is not None else (
        api_config and api_config.get('Relay', {}).get('Stream', False)
    )

    outgoing['model'] = model
    if stream is not None:
        outgoing['stream'] = stream

    # temperature 透传或使用配置默认
    if incoming.get('temperature') is None:
        temp_default = api_config and api_config.get('Relay', {}).get('Temperature')
        if temp_default is not None:
            outgoing['temperature'] = temp_default

    # messages：在首部插入我们自己的 system 提示
    messages: List[Dict[str, str]] = incoming.get('messages') or []
    if not messages:
        raise ValueError("Messages cannot be empty")
    
    # 验证每条消息的格式
    for msg in messages:
        if not isinstance(msg, dict) or not msg.get('role') or not msg.get('content'):
            raise ValueError("Invalid message format")
    
    outgoing['messages'] = [{"role": "system", "content": system_prompt}] + messages

    return outgoing

def proxy_deepseek(payload: Dict[str, Any]) -> Response:
    """将请求代理到华为云 DeepSeek 接口，透传响应（含流式）。"""
    api_key = (api_config and api_config.get('Relay', {}).get('ApiKey')) or os.getenv('DEEPSEEK_API_KEY', '')
    url = (api_config and api_config.get('Relay', {}).get('Url')) or "https://api.modelarts-maas.com/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    want_stream = bool(payload.get('stream'))

    try:
        upstream = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=None if want_stream else 30,
            stream=want_stream,
        )

        # 非200直接透传错误体
        if upstream.status_code != 200:
            return Response(
                upstream.content,
                status=upstream.status_code,
                content_type=upstream.headers.get('Content-Type', 'application/json')
            )

        # 流式：逐块透传上游字节，过滤掉 choices 为空的响应
        if want_stream:
            def generate():
                try:
                    buffer = b""
                    for chunk in upstream.iter_content(chunk_size=8192):
                        if chunk:
                            buffer += chunk
                            # 尝试解析完整的 JSON 块
                            lines = buffer.decode('utf-8', errors='ignore').split('\n')
                            buffer = b""  # 清空缓冲区
                            
                            for line in lines:
                                line = line.strip()
                                if line.startswith('data: ') and len(line) > 6:
                                    try:
                                        data_str = line[6:]  # 移除 'data: ' 前缀
                                        if data_str.strip() != '[DONE]':
                                            data = json.loads(data_str)
                                            # 检查 choices 是否为空
                                            if data.get('choices') and len(data['choices']) > 0:
                                                yield (line + '\n').encode('utf-8')
                                            # 如果 choices 为空，跳过这个响应块
                                    except json.JSONDecodeError:
                                        # JSON 解析失败，可能是部分数据，继续累积
                                        if line:
                                            buffer += (line + '\n').encode('utf-8')
                                    except Exception as e:
                                        # 其他错误，记录并跳过
                                        error_data = f"data: {json.dumps({'error': f'Filter error: {str(e)}'})}\n\n"
                                        yield error_data.encode('utf-8')
                except Exception as e:
                    # 记录流式处理中的错误
                    error_chunk = f"data: {json.dumps({'error': f'Stream error: {str(e)}'})}\n\n"
                    yield error_chunk.encode('utf-8')
                finally:
                    upstream.close()

            return Response(
                stream_with_context(generate()),
                status=200,
                content_type=upstream.headers.get('Content-Type', 'text/event-stream')
            )

        # 非流式：验证并过滤响应数据
        try:
            response_data = upstream.json()
            # 检查 choices 是否为空
            if response_data.get('choices') and len(response_data['choices']) > 0:
                return Response(
                    upstream.content,
                    status=upstream.status_code,
                    content_type=upstream.headers.get('Content-Type', 'application/json')
                )
            else:
                # 如果 choices 为空，返回错误响应
                error_response = {
                    "error": "Empty choices in response",
                    "original_response": response_data
                }
                return Response(
                    json.dumps(error_response, ensure_ascii=False),
                    status=500,
                    content_type='application/json'
                )
        except ValueError:
            # 如果不是有效的 JSON，直接透传原始响应
            return Response(
                upstream.content,
                status=upstream.status_code,
                content_type=upstream.headers.get('Content-Type', 'application/json')
            )

    except Exception as e:
        return Response(json.dumps({"error": str(e)}, ensure_ascii=False), status=500, content_type='application/json')

@app.route(config['routes']['zotero'], methods=['POST'])
def zotero_proxy():
    """Zotero 代理端点

    - 判断最后一条 user 文本是单词还是句子，选择不同的 system 提示词。
    - 构造 payload 并透传给上游大模型接口（含流式）。
    - 响应体保持与上游一致的数据结构与Content-Type。
    """
    try:
        request_data = request.get_json(silent=True)
        if not isinstance(request_data, dict):
            return jsonify({"error": "Invalid request"}), 400

        messages = request_data.get('messages') or []
        # 尝试从最后一条 user 消息中取文本
        user_message_text: Optional[str] = None
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get('role') == 'user':
                user_message_text = (msg.get('content') or '').strip()
                break

        if not user_message_text:
            return jsonify({"error": "Empty message"}), 400

        # 根据词/句选择提示词
        is_word_input = is_word(user_message_text)

        # 构造转发payload（尽量透传原始字段）
        outgoing = build_outgoing_payload(request_data, is_word_input)
        
        # 验证构造的payload
        if not outgoing.get('model'):
            outgoing['model'] = "DeepSeek-V3"  # 确保有有效的模型名称
        
        if not outgoing.get('messages'):
            return jsonify({"error": "Invalid messages format"}), 400

        # 代理到上游并按需流式输出
        return proxy_deepseek(outgoing)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route(config['routes']['anx_reader'], methods=['POST'])
def anx_reader_proxy():
    """Anx-Reader 代理端点

    - 判断最后一条 user 文本是单词还是句子，选择不同的 system 提示词。
    - 构造 payload 并透传给上游大模型接口（含流式）。
    - 响应体保持与上游一致的数据结构与Content-Type。
    """
    try:
        request_data = request.get_json(silent=True)
        if not isinstance(request_data, dict):
            return jsonify({"error": "Invalid request"}), 400

        messages = request_data.get('messages') or []
        # 尝试从最后一条 user 消息中取文本
        user_message_text: Optional[str] = None
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get('role') == 'user':
                user_message_text = (msg.get('content') or '').strip()
                break

        if not user_message_text:
            return jsonify({"error": "Empty message"}), 400

        # 根据词/句选择提示词
        is_word_input = is_word(user_message_text)

        # 构造转发payload（尽量透传原始字段）
        outgoing = build_outgoing_payload(request_data, is_word_input)

        # 代理到上游并按需流式输出
        return proxy_deepseek(outgoing)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"})

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "message": "翻译服务",
        "version": "1.0.0",
        "endpoints": config.get('routes', {})
    })

if __name__ == '__main__':
    app.run(
        host=config['server']['host'],
        port=config['server']['port'],
        debug=config['server']['debug'],
        threaded=config['server']['threaded']
    )

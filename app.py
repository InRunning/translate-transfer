from flask import Flask, request, jsonify, Response
from flask import stream_with_context
import requests
import json
import os
import re
import unicodedata
import yaml
import time
from typing import Any, Dict, List, Optional
from database import init_db, get_cached_word, cache_word_translation

def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "server": {"host": "0.0.0.0", "port": 10283, "debug": True, "threaded": True},
            "routes": {
                "zotero": "/zotero",
                "chat_completions": "/chat/completions",
                "anx_reader": "/anx-reader",
                "health": "/health",
                "index": "/"
            }
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

# 初始化数据库
init_db()

def is_word(text):
    """检测是否为单词"""
    return bool(re.match(r'^[a-zA-Z]{1,50}$', normalize_word_text(text)))

def normalize_word_text(text: str) -> str:
    """移除标点后返回文本，用于单词判定、翻译和音标展示。"""
    return ''.join(
        char for char in text.strip()
        if not unicodedata.category(char).startswith('P')
    ).strip()

def extract_user_message_text(messages: List[Dict[str, str]]) -> Optional[str]:
    """从最后一条 user 消息中提取要翻译的文本。"""
    for i, msg in enumerate(reversed(messages)):
        print(f"检查消息 {i}: {msg}")
        if isinstance(msg, dict) and msg.get('role') == 'user':
            user_message_text = (msg.get('content') or '').strip()
            print(f"找到用户消息: '{user_message_text}'")

            source_match = re.search(r'sourceText:\s*(.+?)(?:\n|$)', user_message_text)
            if source_match:
                actual_word = source_match.group(1).strip()
                print(f"提取到的实际单词: '{actual_word}'")
                user_message_text = actual_word

            return user_message_text

    return None

def build_outgoing_payload(
    incoming: Dict[str, Any],
    is_word_input: bool,
    user_text_override: Optional[str] = None,
) -> Dict[str, Any]:
    """基于入参构造转发给大模型的payload，并按词/句插入不同的system prompt。

    - 尽量透传原始字段，仅覆盖必要字段（model/stream/messages/temperature默认）。
    - messages 最前插入我们自定义的 system 提示词，其余保持入参顺序不变。
    """
    # 选择词/句不同的 system prompt
    if is_word_input:
        system_prompt = (
            "你是一个智能翻译助手，下面是单词，你需要给出该单词最常用的一个释义，并给出美式音标和英式音标，示例：输入：example 输出格式: 例子\n 美式音标：/ɪɡˈzæmpəl/ \n英式音标：/ɪɡˈzɑːmpəl/ ./no_think"
        )
    else:
        system_prompt = (
            "你是一个智能翻译助手，下面是句子，请给出该句子的释义。示例：输入：I want to go home 输出: 我想回家 ./no_think"
        )

    outgoing = dict(incoming)  # 透传基础字段

    # 覆盖/补全必要字段
    configured_model = api_config and api_config.get('Relay', {}).get('Model')
    incoming_model = incoming.get('model')
    model = configured_model or incoming_model or "DeepSeek-V3"
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

    outgoing_messages = [dict(msg) for msg in messages]
    if user_text_override is not None:
        for index in range(len(outgoing_messages) - 1, -1, -1):
            if outgoing_messages[index].get('role') == 'user':
                outgoing_messages[index]['content'] = user_text_override
                break

    outgoing['messages'] = [{"role": "system", "content": system_prompt}] + outgoing_messages

    # 记录模型选择，便于排查前端传入模型名与上游模型不一致的问题。
    if configured_model and incoming_model and configured_model != incoming_model:
        print(
            "检测到客户端模型与上游配置模型不一致，"
            f"已使用 Relay.Model。incoming_model='{incoming_model}', "
            f"relay_model='{configured_model}'"
        )

    return outgoing

def proxy_deepseek(payload: Dict[str, Any], word: Optional[str] = None) -> Response:
    """将请求代理到华为云 DeepSeek 接口，透传响应（含流式）。

    Args:
        payload: 要发送的请求数据
        word: 要翻译的单词，如果提供则先检查缓存
    """
    # 检查缓存是否启用
    cache_enabled = api_config and api_config.get('Relay', {}).get('Cache', True)

    # 如果是单词翻译且缓存启用，先检查缓存
    if word and cache_enabled:
        cached_result = get_cached_word(word)
        if cached_result:
            # 直接使用缓存内容
            cache_content = cached_result['translation_result']

            # 检查是否需要流式响应
            want_stream = bool(payload.get('stream'))

            if want_stream:
                # 流式响应：模拟LLM的流式输出
                def generate():
                    # 生成初始chunk（包含id等基本信息）
                    initial_chunk = {
                        "id": f"chat-{os.urandom(4).hex()}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": payload.get('model', 'DeepSeek-V3'),
                        "choices": [{
                            "index": 0,
                            "delta": {"content": ""},
                            "logprobs": None,
                            "finish_reason": None
                        }],
                        "usage": {"prompt_tokens": 0, "total_tokens": 0, "completion_tokens": 0}
                    }
                    yield f"data: {json.dumps(initial_chunk, ensure_ascii=False)}\n\n".encode('utf-8')

                    # 逐字符输出内容
                    for char in cache_content:
                        chunk = {
                            "id": initial_chunk["id"],
                            "object": "chat.completion.chunk",
                            "created": initial_chunk["created"],
                            "model": initial_chunk["model"],
                            "choices": [{
                                "index": 0,
                                "delta": {"content": char},
                                "logprobs": None,
                                "finish_reason": None
                            }],
                            "usage": {"prompt_tokens": 0, "total_tokens": 0, "completion_tokens": 0}
                        }
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode('utf-8')

                    # 生成结束chunk
                    final_chunk = {
                        "id": initial_chunk["id"],
                        "object": "chat.completion.chunk",
                        "created": initial_chunk["created"],
                        "model": initial_chunk["model"],
                        "choices": [{
                            "index": 0,
                            "delta": {"content": ""},
                            "logprobs": None,
                            "finish_reason": "stop",
                            "stop_reason": None
                        }],
                        "usage": {
                            "prompt_tokens": 78,
                            "total_tokens": 106,
                            "completion_tokens": len(cache_content) # type: ignore
                        }
                    }
                    yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n".encode('utf-8')

                return Response(
                    stream_with_context(generate()),
                    status=200,
                    content_type='text/event-stream'
                )
            else:
                # 非流式响应：保持原有逻辑
                response_data = {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": cache_content
                        }
                    }]
                }
                return Response(
                    json.dumps(response_data, ensure_ascii=False),
                    status=200,
                    content_type='application/json'
                )

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
            # 如果没有缓存，继续正常的流式处理
            translation_buffer = ""  # 用于累积翻译内容

            def generate_stream():
                nonlocal translation_buffer
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
                                                # 累积翻译内容用于缓存
                                                if data['choices'][0].get('delta', {}).get('content'):
                                                    translation_buffer += data['choices'][0]['delta']['content']

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
                    # 流式结束后，如果有单词且缓存启用且没有缓存，则缓存结果
                    if word and translation_buffer and cache_enabled and not get_cached_word(word):
                        # 直接缓存完整的翻译结果
                        cache_word_translation(word, translation_buffer)

                    upstream.close()

            return Response(
                stream_with_context(generate_stream()),
                status=200,
                content_type=upstream.headers.get('Content-Type', 'text/event-stream')
            )

        # 非流式：验证并过滤响应数据
        try:
            response_data = upstream.json()
            # 检查 choices 是否为空
            if response_data.get('choices') and len(response_data['choices']) > 0:
                # 如果是单词翻译且缓存启用且没有缓存，则缓存结果
                if word and cache_enabled and not get_cached_word(word):
                    assistant_message = response_data['choices'][0]['message']['content']
                    # 直接缓存完整的翻译结果
                    cache_word_translation(word, assistant_message)

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

@app.route('/zotero/json', methods=['POST'])
def zotero_json_proxy():
    """Zotero 代理端点（非流式JSON响应）

    这个端点总是返回标准的JSON响应，兼容Apifox等工具。
    """
    try:
        # 记录原始请求内容用于调试
        raw_content = request.get_data(as_text=True)
        print(f"Zotero JSON 原始请求内容: {raw_content}")
        print(f"请求 Content-Type: {request.content_type}")

        # 检查 Content-Type
        content_type = request.content_type or ''
        if 'application/json' not in content_type:
            print(f"警告: Content-Type 不是 application/json: {content_type}")

        request_data = request.get_json(silent=True)
        if request_data is None:
            # 详细说明JSON解析失败的原因
            error_msg = f"请求中不包含有效的 JSON。原始内容: {raw_content[:200]}..."
            print(f"JSON解析失败: {error_msg}")
            return jsonify({
                "error": error_msg,
                "details": "请检查请求格式是否正确",
                "hint": "确保请求头包含 'Content-Type: application/json'"
            }), 400

        if not isinstance(request_data, dict):
            return jsonify({"error": f"Invalid request data type: {type(request_data)}"}), 400

        print(f"解析后的请求数据: {request_data}")

        messages = request_data.get('messages') or []
        print(f"Messages 数量: {len(messages)}")

        # 尝试从最后一条 user 消息中取文本
        user_message_text = extract_user_message_text(messages)

        if not user_message_text:
            return jsonify({
                "error": "Empty message",
                "details": "无法从请求中提取有效的用户消息内容",
                "messages": messages
            }), 400

        normalized_word_text = normalize_word_text(user_message_text)
        is_word_input = is_word(user_message_text)
        effective_user_text = normalized_word_text if is_word_input else user_message_text
        print(
            f"是否为单词输入: {is_word_input}, 原文本: '{user_message_text}', "
            f"规范化后: '{effective_user_text}'"
        )

        # 添加缓存检查日志
        if is_word_input:
            cache_enabled = api_config and api_config.get('Relay', {}).get('Cache', True)
            print(f"缓存启用状态: {cache_enabled}")
            if cache_enabled:
                cached_result = get_cached_word(effective_user_text)
                print(f"缓存检查结果: {'命中' if cached_result else '未命中'}")

        # 构造转发payload（强制非流式）
        outgoing = build_outgoing_payload(
            request_data,
            is_word_input,
            effective_user_text if is_word_input else None,
        )

        # 强制设置为非流式
        outgoing['stream'] = False

        # 验证构造的payload
        if not outgoing.get('model'):
            outgoing['model'] = "DeepSeek-V3"  # 确保有有效的模型名称

        if not outgoing.get('messages'):
            return jsonify({"error": "Invalid messages format", "details": "构造的payload中缺少messages"}), 400

        print(f"构造的payload (非流式): {outgoing}")

        # 代理到上游并返回非流式响应
        return proxy_deepseek(outgoing, effective_user_text if is_word_input else None)

    except Exception as e:
        import traceback
        error_details = f"Zotero JSON 代理错误: {str(e)}\n{traceback.format_exc()}"
        print(error_details)
        return jsonify({
            "error": str(e),
            "details": "服务器内部错误",
            "traceback": error_details
        }), 500

@app.route(config['routes']['zotero'], methods=['POST'])
def zotero_proxy(force_stream: Optional[bool] = None):
    """Zotero 代理端点

    - 判断最后一条 user 文本是单词还是句子，选择不同的 system 提示词。
    - 构造 payload 并透传给上游大模型接口（含流式）。
    - 响应体保持与上游一致的数据结构与Content-Type。
    """
    try:
        # 记录原始请求内容用于调试
        raw_content = request.get_data(as_text=True)
        print(f"Zotero 原始请求内容: {raw_content}")
        print(f"请求 Content-Type: {request.content_type}")

        # 检查 Content-Type
        content_type = request.content_type or ''
        if 'application/json' not in content_type:
            print(f"警告: Content-Type 不是 application/json: {content_type}")

        request_data = request.get_json(silent=True)
        if request_data is None:
            # 详细说明JSON解析失败的原因
            error_msg = f"请求中不包含有效的 JSON。原始内容: {raw_content[:200]}..."
            print(f"JSON解析失败: {error_msg}")
            return jsonify({
                "error": error_msg,
                "details": "请检查请求格式是否正确",
                "hint": "确保请求头包含 'Content-Type: application/json'"
            }), 400

        if not isinstance(request_data, dict):
            return jsonify({"error": f"Invalid request data type: {type(request_data)}"}), 400

        print(f"解析后的请求数据: {request_data}")

        messages = request_data.get('messages') or []
        print(f"Messages 数量: {len(messages)}")

        # 尝试从最后一条 user 消息中取文本
        user_message_text = extract_user_message_text(messages)

        if not user_message_text:
            return jsonify({
                "error": "Empty message",
                "details": "无法从请求中提取有效的用户消息内容",
                "messages": messages
            }), 400

        normalized_word_text = normalize_word_text(user_message_text)
        is_word_input = is_word(user_message_text)
        effective_user_text = normalized_word_text if is_word_input else user_message_text
        print(
            f"是否为单词输入: {is_word_input}, 原文本: '{user_message_text}', "
            f"规范化后: '{effective_user_text}'"
        )

        # 构造转发payload（尽量透传原始字段）
        outgoing = build_outgoing_payload(
            request_data,
            is_word_input,
            effective_user_text if is_word_input else None,
        )
        if force_stream is not None:
            outgoing['stream'] = force_stream

        # 验证构造的payload
        if not outgoing.get('model'):
            outgoing['model'] = "DeepSeek-V3"  # 确保有有效的模型名称

        if not outgoing.get('messages'):
            return jsonify({"error": "Invalid messages format", "details": "构造的payload中缺少messages"}), 400

        print(f"构造的payload: {outgoing}")

        # 代理到上游并按需流式输出，如果是单词则传递单词参数
        return proxy_deepseek(outgoing, effective_user_text if is_word_input else None)

    except Exception as e:
        import traceback
        error_details = f"Zotero 代理错误: {str(e)}\n{traceback.format_exc()}"
        print(error_details)
        return jsonify({
            "error": str(e),
            "details": "服务器内部错误",
            "traceback": error_details
        }), 500

@app.route(config['routes']['anx_reader'], methods=['POST'])
def anx_reader_proxy():
    """Anx-Reader 代理端点

    - 判断最后一条 user 文本是单词还是句子，选择不同的 system 提示词。
    - 构造 payload 并透传给上游大模型接口（含流式）。
    - 响应体保持与上游一致的数据结构与Content-Type。
    """
    try:
        # 记录原始请求内容用于调试
        raw_content = request.get_data(as_text=True)
        print(f"Anx-Reader 原始请求内容: {raw_content}")
        print(f"请求 Content-Type: {request.content_type}")

        # 检查 Content-Type
        content_type = request.content_type or ''
        if 'application/json' not in content_type:
            print(f"警告: Content-Type 不是 application/json: {content_type}")

        request_data = request.get_json(silent=True)
        if request_data is None:
            # 详细说明JSON解析失败的原因
            error_msg = f"请求中不包含有效的 JSON。原始内容: {raw_content[:200]}..."
            print(f"JSON解析失败: {error_msg}")
            return jsonify({
                "error": error_msg,
                "details": "请检查请求格式是否正确",
                "hint": "确保请求头包含 'Content-Type: application/json'"
            }), 400

        if not isinstance(request_data, dict):
            return jsonify({"error": f"Invalid request data type: {type(request_data)}"}), 400

        print(f"解析后的请求数据: {request_data}")

        messages = request_data.get('messages') or []
        print(f"Messages 数量: {len(messages)}")

        # 尝试从最后一条 user 消息中取文本
        user_message_text = extract_user_message_text(messages)

        if not user_message_text:
            return jsonify({
                "error": "Empty message",
                "details": "无法从请求中提取有效的用户消息内容",
                "messages": messages
            }), 400

        normalized_word_text = normalize_word_text(user_message_text)
        is_word_input = is_word(user_message_text)
        effective_user_text = normalized_word_text if is_word_input else user_message_text
        print(
            f"是否为单词输入: {is_word_input}, 原文本: '{user_message_text}', "
            f"规范化后: '{effective_user_text}'"
        )

        # 构造转发payload（尽量透传原始字段）
        outgoing = build_outgoing_payload(
            request_data,
            is_word_input,
            effective_user_text if is_word_input else None,
        )

        # 验证构造的payload
        if not outgoing.get('model'):
            outgoing['model'] = "DeepSeek-V3"  # 确保有有效的模型名称

        if not outgoing.get('messages'):
            return jsonify({"error": "Invalid messages format", "details": "构造的payload中缺少messages"}), 400

        print(f"构造的payload: {outgoing}")

        # 代理到上游并按需流式输出，如果是单词则传递单词参数
        return proxy_deepseek(outgoing, effective_user_text if is_word_input else None)

    except Exception as e:
        import traceback
        error_details = f"Anx-Reader 代理错误: {str(e)}\n{traceback.format_exc()}"
        print(error_details)
        return jsonify({
            "error": str(e),
            "details": "服务器内部错误",
            "traceback": error_details
        }), 500

@app.route('/anx-reader/chat/completions', methods=['POST'])
def anx_reader_chat_completions_proxy():
    """Anx-Reader Chat Completions 代理端点

    功能与 /anx-reader 完全相同，只是路径不同。
    """
    return anx_reader_proxy()

@app.route('/anx-reader/v1/chat/completions', methods=['POST'])
def anx_reader_v1_chat_completions_proxy():
    """Anx-Reader V1 Chat Completions 代理端点

    功能与 /anx-reader 完全相同，只是路径不同。
    """
    return anx_reader_proxy()

@app.route(config['routes']['chat_completions'], methods=['POST'])
def chat_completions_proxy():
    """Chat Completions 兼容代理端点

    功能与 /zotero 基本相同，但强制使用非流式 HTTP 响应。
    """
    return zotero_proxy(force_stream=False)

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

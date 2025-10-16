from flask import Flask, request, jsonify, Response
from flask import stream_with_context
import requests
import json
import os
import re
import yaml
import sqlite3
import time
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

# SQLite 数据库初始化
def init_db():
    """初始化 SQLite 数据库，创建单词翻译缓存表"""
    conn = sqlite3.connect('word_cache.db')
    cursor = conn.cursor()
    
    # 创建单词翻译缓存表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS word_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL,
            definition TEXT NOT NULL,
            us_phonetic TEXT,
            uk_phonetic TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建索引以提高查询性能
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_word ON word_cache(word)')
    
    conn.commit()
    conn.close()

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect('word_cache.db')
    conn.row_factory = sqlite3.Row  # 返回字典形式的行
    return conn

def get_cached_word(word: str) -> Optional[Dict[str, str]]:
    """从缓存中获取单词翻译结果"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT word, definition, us_phonetic, uk_phonetic
        FROM word_cache
        WHERE word = ?
    ''', (word.lower(),))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'word': result['word'],
            'definition': result['definition'],
            'us_phonetic': result['us_phonetic'],
            'uk_phonetic': result['uk_phonetic']
        }
    return None

def cache_word_translation(word: str, definition: str, us_phonetic: Optional[str] = None, uk_phonetic: Optional[str] = None):
    """缓存单词翻译结果"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO word_cache (word, definition, us_phonetic, uk_phonetic, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (word.lower(), definition, us_phonetic, uk_phonetic))
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        return False
    finally:
        conn.close()

def parse_translation_result(translation_text: str, word: str) -> tuple:
    """解析翻译结果，提取释义、美式音标、英式音标
    
    Args:
        translation_text: 翻译结果文本
        word: 原始单词
        
    Returns:
        tuple: (definition, us_phonetic, uk_phonetic)
    """
    import re
    
    definition = ""
    us_phonetic = ""
    uk_phonetic = ""
    
    # 提取释义（第一行通常是释义）
    lines = translation_text.strip().split('\n')
    if lines:
        definition = lines[0].strip()
    
    # 提取美式音标
    us_match = re.search(r'美式音标：([^,，]+)', translation_text)
    if us_match:
        us_phonetic = us_match.group(1).strip()
    
    # 提取英式音标
    uk_match = re.search(r'英式音标：([^\s,，]+)', translation_text)
    if uk_match:
        uk_phonetic = uk_match.group(1).strip()
    
    return definition, us_phonetic, uk_phonetic

# 初始化数据库
init_db()

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
            # 构建缓存内容
            cache_content = f"{cached_result['definition']}\n美式音标：{cached_result['us_phonetic'] or 'N/A'}, 英式音标：{cached_result['uk_phonetic'] or 'N/A'}"
            
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
                            "completion_tokens": len(cache_content)
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
                        # 解析翻译结果，提取释义、美式音标、英式音标
                        definition, us_phonetic, uk_phonetic = parse_translation_result(translation_buffer, word)
                        if definition:
                            cache_word_translation(word, definition, us_phonetic, uk_phonetic)
                    
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
                    # 解析翻译结果，提取释义、美式音标、英式音标
                    definition, us_phonetic, uk_phonetic = parse_translation_result(assistant_message, word)
                    if definition:
                        cache_word_translation(word, definition, us_phonetic, uk_phonetic)
                
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
        user_message_text: Optional[str] = None
        for i, msg in enumerate(reversed(messages)):
            print(f"检查消息 {i}: {msg}")
            if isinstance(msg, dict) and msg.get('role') == 'user':
                user_message_text = (msg.get('content') or '').strip()
                print(f"找到用户消息: '{user_message_text}'")
                
                # 尝试提取实际的单词文本
                import re
                # 查找 sourceText: 后面的内容
                source_match = re.search(r'sourceText:\s*(.+?)(?:\n|$)', user_message_text)
                if source_match:
                    actual_word = source_match.group(1).strip()
                    print(f"提取到的实际单词: '{actual_word}'")
                    # 替换用户消息文本为纯单词
                    user_message_text = actual_word
                break

        if not user_message_text:
            return jsonify({
                "error": "Empty message",
                "details": "无法从请求中提取有效的用户消息内容",
                "messages": messages
            }), 400

        # 根据词/句选择提示词
        is_word_input = is_word(user_message_text)
        print(f"是否为单词输入: {is_word_input}, 文本: '{user_message_text}'")
        
        # 添加缓存检查日志
        if is_word_input:
            cache_enabled = api_config and api_config.get('Relay', {}).get('Cache', True)
            print(f"缓存启用状态: {cache_enabled}")
            if cache_enabled:
                cached_result = get_cached_word(user_message_text)
                print(f"缓存检查结果: {'命中' if cached_result else '未命中'}")
        
        # 添加缓存检查日志
        if is_word_input:
            cache_enabled = api_config and api_config.get('Relay', {}).get('Cache', True)
            print(f"缓存启用状态: {cache_enabled}")
            if cache_enabled:
                cached_result = get_cached_word(user_message_text)
                print(f"缓存检查结果: {'命中' if cached_result else '未命中'}")
        
        # 添加缓存检查日志
        if is_word_input:
            cache_enabled = api_config and api_config.get('Relay', {}).get('Cache', True)
            print(f"缓存启用状态: {cache_enabled}")
            if cache_enabled:
                cached_result = get_cached_word(user_message_text)
                print(f"缓存检查结果: {'命中' if cached_result else '未命中'}")

        # 构造转发payload（强制非流式）
        outgoing = build_outgoing_payload(request_data, is_word_input)
        
        # 强制设置为非流式
        outgoing['stream'] = False
        
        # 验证构造的payload
        if not outgoing.get('model'):
            outgoing['model'] = "DeepSeek-V3"  # 确保有有效的模型名称
        
        if not outgoing.get('messages'):
            return jsonify({"error": "Invalid messages format", "details": "构造的payload中缺少messages"}), 400

        print(f"构造的payload (非流式): {outgoing}")

        # 代理到上游并返回非流式响应
        return proxy_deepseek(outgoing, user_message_text if is_word_input else None)

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
def zotero_proxy():
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
        user_message_text: Optional[str] = None
        for i, msg in enumerate(reversed(messages)):
            print(f"检查消息 {i}: {msg}")
            if isinstance(msg, dict) and msg.get('role') == 'user':
                user_message_text = (msg.get('content') or '').strip()
                print(f"找到用户消息: '{user_message_text}'")
                
                # 尝试提取实际的单词文本
                import re
                # 查找 sourceText: 后面的内容
                source_match = re.search(r'sourceText:\s*(.+?)(?:\n|$)', user_message_text)
                if source_match:
                    actual_word = source_match.group(1).strip()
                    print(f"提取到的实际单词: '{actual_word}'")
                    # 替换用户消息文本为纯单词
                    user_message_text = actual_word
                break

        if not user_message_text:
            return jsonify({
                "error": "Empty message",
                "details": "无法从请求中提取有效的用户消息内容",
                "messages": messages
            }), 400

        # 根据词/句选择提示词
        is_word_input = is_word(user_message_text)
        print(f"是否为单词输入: {is_word_input}, 文本: '{user_message_text}'")

        # 构造转发payload（尽量透传原始字段）
        outgoing = build_outgoing_payload(request_data, is_word_input)
        
        # 验证构造的payload
        if not outgoing.get('model'):
            outgoing['model'] = "DeepSeek-V3"  # 确保有有效的模型名称
        
        if not outgoing.get('messages'):
            return jsonify({"error": "Invalid messages format", "details": "构造的payload中缺少messages"}), 400

        print(f"构造的payload: {outgoing}")

        # 代理到上游并按需流式输出，如果是单词则传递单词参数
        return proxy_deepseek(outgoing, user_message_text if is_word_input else None)

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
        user_message_text: Optional[str] = None
        for i, msg in enumerate(reversed(messages)):
            print(f"检查消息 {i}: {msg}")
            if isinstance(msg, dict) and msg.get('role') == 'user':
                user_message_text = (msg.get('content') or '').strip()
                print(f"找到用户消息: '{user_message_text}'")
                
                # 尝试提取实际的单词文本
                import re
                # 查找 sourceText: 后面的内容
                source_match = re.search(r'sourceText:\s*(.+?)(?:\n|$)', user_message_text)
                if source_match:
                    actual_word = source_match.group(1).strip()
                    print(f"提取到的实际单词: '{actual_word}'")
                    # 替换用户消息文本为纯单词
                    user_message_text = actual_word
                break

        if not user_message_text:
            return jsonify({
                "error": "Empty message",
                "details": "无法从请求中提取有效的用户消息内容",
                "messages": messages
            }), 400

        # 根据词/句选择提示词
        is_word_input = is_word(user_message_text)
        print(f"是否为单词输入: {is_word_input}, 文本: '{user_message_text}'")

        # 构造转发payload（尽量透传原始字段）
        outgoing = build_outgoing_payload(request_data, is_word_input)
        
        # 验证构造的payload
        if not outgoing.get('model'):
            outgoing['model'] = "DeepSeek-V3"  # 确保有有效的模型名称
        
        if not outgoing.get('messages'):
            return jsonify({"error": "Invalid messages format", "details": "构造的payload中缺少messages"}), 400

        print(f"构造的payload: {outgoing}")

        # 代理到上游并按需流式输出，如果是单词则传递单词参数
        return proxy_deepseek(outgoing, user_message_text if is_word_input else None)

    except Exception as e:
        import traceback
        error_details = f"Anx-Reader 代理错误: {str(e)}\n{traceback.format_exc()}"
        print(error_details)
        return jsonify({
            "error": str(e),
            "details": "服务器内部错误",
            "traceback": error_details
        }), 500

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

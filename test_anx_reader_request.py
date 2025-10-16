#!/usr/bin/env python3
"""
测试anx-reader端点的请求格式
"""

import requests
import json
import sys

def test_anx_reader_request():
    """测试anx-reader端点的各种请求格式"""
    
    base_url = "http://localhost:10283"
    
    # 测试用例1：标准的OpenAI格式请求
    test_cases = [
        {
            "name": "标准OpenAI格式 - 单词翻译",
            "data": {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "user", "content": "hello"}
                ],
                "stream": False
            }
        },
        {
            "name": "标准OpenAI格式 - 句子翻译", 
            "data": {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "user", "content": "I want to go home"}
                ],
                "stream": False
            }
        },
        {
            "name": "标准OpenAI格式 - 流式翻译",
            "data": {
                "model": "gpt-3.5-turbo", 
                "messages": [
                    {"role": "user", "content": "world"}
                ],
                "stream": True
            }
        },
        {
            "name": "空messages",
            "data": {
                "model": "gpt-3.5-turbo",
                "messages": [],
                "stream": False
            }
        },
        {
            "name": "无messages字段",
            "data": {
                "model": "gpt-3.5-turbo",
                "stream": False
            }
        },
        {
            "name": "无效JSON",
            "data": "invalid json content"
        }
    ]
    
    print("=== Anx-Reader 端点测试 ===\n")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"测试用例 {i}: {test_case['name']}")
        print(f"请求数据: {json.dumps(test_case['data'], ensure_ascii=False)}")
        
        try:
            response = requests.post(
                f"{base_url}/anx-reader",
                json=test_case['data'],
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            print(f"状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            
            if response.status_code == 200:
                print("✅ 请求成功")
            else:
                print("❌ 请求失败")
                
        except requests.exceptions.ConnectionError:
            print("❌ 无法连接到服务器，请确保服务正在运行 (python app.py)")
        except Exception as e:
            print(f"❌ 请求异常: {str(e)}")
        
        print("-" * 50)

if __name__ == "__main__":
    test_anx_reader_request()
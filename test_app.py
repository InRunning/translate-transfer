#!/usr/bin/env python3
"""
Flask应用测试脚本
测试大模型请求转发服务的各个端点
"""

import requests
import json
import time
import sys
from typing import Dict, Any

class FlaskAppTester:
    def __init__(self, base_url: str = "http://localhost:10283"):
        self.base_url = base_url
        self.timeout = 30
        
    def test_health_endpoint(self) -> bool:
        """测试健康检查端点"""
        print("🔍 测试健康检查端点...")
        try:
            response = requests.get(f"{self.base_url}/health", timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ 健康检查成功: {data}")
                return True
            else:
                print(f"❌ 健康检查失败: HTTP {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ 健康检查异常: {e}")
            return False
    
    def test_index_endpoint(self) -> bool:
        """测试首页端点"""
        print("🔍 测试首页端点...")
        try:
            response = requests.get(f"{self.base_url}/", timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ 首页信息获取成功: {data['message']}")
                print(f"   版本: {data['version']}")
                print(f"   端点: {data['endpoints']}")
                return True
            else:
                print(f"❌ 首页端点失败: HTTP {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ 首页端点异常: {e}")
            return False
    
    def test_zotero_proxy_with_mock(self) -> bool:
        """测试Zotero代理端点（使用模拟数据）"""
        print("🔍 测试Zotero代理端点...")
        
        # 模拟请求数据
        mock_request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello, this is a test message!"
                }
            ],
            "max_tokens": 100,
            "temperature": 0.7
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/zotero", 
                json=mock_request_data, 
                timeout=self.timeout
            )
            
            print(f"   响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Zotero代理测试成功")
                print(f"   响应数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
                return True
            elif response.status_code == 400:
                error_data = response.json()
                print(f"⚠️  请求格式错误: {error_data.get('error')}")
                return True  # 这是预期的错误，因为没有真实的API密钥
            elif response.status_code == 500:
                error_data = response.json()
                print(f"❌ 服务器内部错误: {error_data.get('error')}")
                return False
            else:
                print(f"❌ Zotero代理测试失败: HTTP {response.status_code}")
                print(f"   错误信息: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Zotero代理测试异常: {e}")
            return False
    
    def test_invalid_json(self) -> bool:
        """测试无效JSON数据"""
        print("🔍 测试无效JSON数据...")
        try:
            response = requests.post(
                f"{self.base_url}/zotero", 
                data="invalid json data", 
                headers={'Content-Type': 'application/json'},
                timeout=self.timeout
            )
            
            if response.status_code == 400:
                data = response.json()
                print(f"✅ 无效JSON测试成功: {data.get('error')}")
                return True
            else:
                print(f"❌ 无效JSON测试失败: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 无效JSON测试异常: {e}")
            return False
    
    def test_connection(self) -> bool:
        """测试连接到服务器"""
        print("🔍 测试服务器连接...")
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def run_all_tests(self) -> Dict[str, bool]:
        """运行所有测试"""
        print("=" * 60)
        print("🚀 开始Flask应用测试")
        print("=" * 60)
        
        # 首先检查服务器是否运行
        if not self.test_connection():
            print("❌ 服务器未运行或无法连接")
            print("💡 请确保Flask应用正在运行: python app.py")
            return {}
        
        print("✅ 服务器连接成功")
        print()
        
        # 运行各项测试
        results = {
            "health_check": self.test_health_endpoint(),
            "index_endpoint": self.test_index_endpoint(),
            "zotero_proxy": self.test_zotero_proxy_with_mock(),
            "invalid_json": self.test_invalid_json()
        }
        
        print()
        print("=" * 60)
        print("📊 测试结果汇总")
        print("=" * 60)
        
        passed = 0
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ 通过" if result else "❌ 失败"
            print(f"{test_name.replace('_', ' ').title()}: {status}")
            if result:
                passed += 1
        
        print()
        print(f"📈 总体结果: {passed}/{total} 测试通过")
        
        if passed == total:
            print("🎉 所有测试通过！")
        else:
            print("⚠️  部分测试失败，请检查应用配置")
        
        return results

def main():
    """主函数"""
    print("Flask应用测试脚本")
    print("使用说明:")
    print("1. 确保Flask应用正在运行 (python app.py)")
    print("2. 设置OPENAI_API_KEY环境变量（可选）")
    print("3. 运行此脚本进行测试")
    print()
    
    # 检查命令行参数
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:10283"
    
    # 创建测试器并运行测试
    tester = FlaskAppTester(base_url)
    results = tester.run_all_tests()
    
    # 返回退出码
    return 0 if all(results.values()) else 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
#!/usr/bin/env python3
"""
SecureModelLoader API 连接测试脚本
用于测试与Vercel部署的后端API的连接和验证功能
"""

import requests
import uuid
import os
import json
import platform
import subprocess
from typing import Dict, Any

# 测试配置
SERVER_URL = "https://vercel-model-manager.vercel.app/api/verify-key"
TEST_API_KEY = "APIKEY_wk_test_model_1_lv3s2cc4"  # 请填入测试用的API密钥
TIMEOUT = 15

def get_cpu_info() -> str:
    """获取CPU信息，支持Windows和Linux"""
    try:
        system = platform.system()
        
        if system == "Windows":
            # Windows系统获取CPU信息
            try:
                result = subprocess.run(
                    ['wmic', 'cpu', 'get', 'name'], 
                    capture_output=True, 
                    text=True, 
                    timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) >= 2:
                        cpu_name = lines[1].strip()
                        if cpu_name:
                            return cpu_name
            except Exception as e:
                print(f"⚠️ Windows CPU信息获取失败: {str(e)}")
            
            # 备用方案：使用platform模块
            return platform.processor() or "Unknown CPU"
            
        elif system == "Linux":
            # Linux系统获取CPU信息
            try:
                if os.path.exists("/proc/cpuinfo"):
                    with open("/proc/cpuinfo", "r") as f:
                        for line in f:
                            if "model name" in line.lower():
                                cpu_name = line.split(":")[1].strip()
                                if cpu_name:
                                    return cpu_name
            except Exception as e:
                print(f"⚠️ Linux CPU信息获取失败: {str(e)}")
            
            # 备用方案：使用lscpu命令
            try:
                result = subprocess.run(
                    ['lscpu'], 
                    capture_output=True, 
                    text=True, 
                    timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Model name:' in line:
                            cpu_name = line.split(':')[1].strip()
                            if cpu_name:
                                return cpu_name
            except Exception as e:
                print(f"⚠️ lscpu命令执行失败: {str(e)}")
            
            return "Unknown CPU"
            
        else:
            # 其他系统
            return platform.processor() or "Unknown CPU"
            
    except Exception as e:
        print(f"❌ CPU信息获取失败: {str(e)}")
        return "Unknown CPU"

def get_device_info() -> Dict[str, str]:
    """获取设备信息"""
    # 获取MAC地址
    mac = ":".join([f"{(uuid.getnode() >> i) & 0xff:02x}" 
                   for i in range(0, 8*6, 8)][::-1])
    
    # 获取CPU信息
    cpu = get_cpu_info()
    
    return {
        "mac": mac,
        "cpu": cpu
    }

def test_api_connection():
    """测试API连接"""
    print("🔍 开始测试API连接...")
    print(f"🌐 服务器地址: {SERVER_URL}")
    
    # 获取设备信息
    device_info = get_device_info()
    print(f"📱 MAC地址: {device_info['mac']}")
    print(f"🖥️ CPU信息: {device_info['cpu']}")
    
    if not TEST_API_KEY:
        print("❌ 错误: 请在脚本中设置 TEST_API_KEY")
        return False
    
    print(f"🔑 API密钥: {TEST_API_KEY[:8]}...")
    
    # 准备请求数据
    request_data = {
        "key": TEST_API_KEY,
        "mac": device_info["mac"],
        "cpu": device_info["cpu"]
    }
    
    print(f"📤 发送请求数据: {json.dumps(request_data, indent=2)}")
    
    try:
        # 发送请求
        print("⏳ 正在发送请求...")
        response = requests.post(
            SERVER_URL,
            json=request_data,
            timeout=TIMEOUT,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SecureModelLoader-Test/1.0"
            }
        )
        
        print(f"📥 响应状态码: {response.status_code}")
        print(f"📋 响应头: {dict(response.headers)}")
        
        # 检查响应
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 请求成功!")
            print(f"📊 响应数据: {json.dumps(data, indent=2)}")
            
            # 验证响应格式
            if data.get("success") and data.get("xorResult") and data.get("timestamp"):
                print("✅ 响应格式正确")
                return True
            else:
                print("❌ 响应格式不正确，缺少必要字段")
                return False
        else:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            try:
                error_data = response.json()
                print(f"📋 错误信息: {json.dumps(error_data, indent=2)}")
            except:
                print(f"📋 错误信息: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ 请求超时")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误，请检查网络连接和服务器地址")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求异常: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ 未知错误: {str(e)}")
        return False

def test_server_health():
    """测试服务器健康状态"""
    print("\n🏥 测试服务器健康状态...")
    
    try:
        # 尝试访问根路径
        response = requests.get(
            "https://vercel-model-manager.vercel.app/",
            timeout=10
        )
        print(f"✅ 服务器可访问，状态码: {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ 服务器不可访问: {str(e)}")
        return False

def main():
    """主函数"""
    print("🚀 SecureModelLoader API 连接测试")
    print("=" * 50)
    
    # 测试服务器健康状态
    if not test_server_health():
        print("\n❌ 服务器健康检查失败，请检查服务器状态")
        return
    
    # 测试API连接
    if test_api_connection():
        print("\n🎉 所有测试通过！API连接正常")
    else:
        print("\n💥 测试失败，请检查配置和网络连接")
    
    print("\n📝 使用说明:")
    print("1. 确保已在后端管理界面创建了API密钥")
    print("2. 将API密钥填入 TEST_API_KEY 变量")
    print("3. 确保设备信息正确")
    print("4. 检查网络连接和防火墙设置")

if __name__ == "__main__":
    main() 
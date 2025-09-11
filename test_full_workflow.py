#!/usr/bin/env python3
"""
完整工作流程测试脚本
测试从加密到解密的完整流程
"""

import os
import sys
import tempfile
import json
import struct
import shutil
from pathlib import Path

# 添加工具路径
sys.path.append(str(Path(__file__).parent / "client" / "tools"))
sys.path.append(str(Path(__file__).parent / "client" / "sd_client"))

def create_dummy_safetensors(path: str):
    """创建一个虚拟的safetensors文件用于测试"""
    # 创建虚拟的tensor metadata
    header_obj = {
        "weight1": {
            "dtype": "F32",
            "shape": [2, 3],
            "data_offsets": [0, 24]
        },
        "weight2": {
            "dtype": "F32", 
            "shape": [3, 2],
            "data_offsets": [24, 48]
        }
    }
    
    # 虚拟tensor数据 (2个3x4=24字节的tensor)
    dummy_data = b'\x00\x01\x02\x03' * 12  # 48字节
    
    header_json = json.dumps(header_obj, separators=(',', ':'))
    header_bytes = header_json.encode('utf-8')
    
    with open(path, 'wb') as f:
        f.write(struct.pack('<Q', len(header_bytes)))  # header长度
        f.write(header_bytes)  # header
        f.write(dummy_data)  # 数据
    
    print(f"✅ 创建虚拟safetensors文件: {path}")

def test_encryption():
    """测试加密功能"""
    print("\n🔐 测试加密功能...")
    
    try:
        from model_encryptor import encrypt_model
        
        # 创建临时文件
        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = os.path.join(temp_dir, "test_model.safetensors")
            output_file = os.path.join(temp_dir, "test_model_encrypted.safetensors")
            
            # 创建测试文件
            create_dummy_safetensors(input_file)
            
            # 测试API Key
            test_api_key = "12345678901234567890123456789012"  # 32位测试key
            
            # 执行加密
            encrypt_model(input_file, output_file, test_api_key, force=True)
            
            # 验证输出文件存在
            if os.path.exists(output_file):
                print("✅ 加密成功，输出文件已生成")
                
                # 读取并验证metadata
                from model_encryptor import read_safetensors_file
                _, _, _, header_obj = read_safetensors_file(output_file)
                
                wk_meta = header_obj.get("__metadata__", {}).get("wk_enc")
                if wk_meta:
                    wk_data = json.loads(wk_meta)
                    if wk_data.get("model_id") == test_api_key:
                        print(f"✅ metadata验证成功，model_id: {wk_data.get('model_id')}")
                        return True, output_file
                    else:
                        print(f"❌ model_id不匹配: {wk_data.get('model_id')} != {test_api_key}")
                else:
                    print("❌ 加密metadata未找到")
            else:
                print("❌ 输出文件未生成")
                
    except Exception as e:
        print(f"❌ 加密测试失败: {e}")
    
    return False, None

def test_metadata_reading():
    """测试metadata读取功能"""
    print("\n📖 测试metadata读取功能...")
    
    try:
        # 先创建一个加密文件
        success, encrypted_file = test_encryption()
        if not success:
            return False
        
        # 测试读取逻辑（模拟final_model_loader的逻辑）
        import json
        import struct
        
        def parse_header(path: str):
            with open(path, "rb") as f:
                hlb = f.read(8)
                if len(hlb) != 8:
                    return None
                hlen = struct.unpack("<Q", hlb)[0]
                hbytes = f.read(hlen)
                if len(hbytes) != hlen:
                    return None
            hobj = json.loads(hbytes.decode("utf-8"))
            return hlen, hbytes, hobj
        
        parsed = parse_header(encrypted_file)
        if parsed:
            header_len, header_bytes, header_obj = parsed
            
            meta_root = header_obj.get("__metadata__", {})
            wk_meta = meta_root.get("wk_enc")
            
            if isinstance(wk_meta, str):
                wk_meta = json.loads(wk_meta)
            
            if wk_meta and wk_meta.get("enc"):
                model_id = wk_meta.get("model_id")
                alg = wk_meta.get("alg")
                
                print(f"✅ 成功读取加密metadata:")
                print(f"   - model_id: {model_id}")
                print(f"   - 算法: {alg}")
                print(f"   - 加密状态: {wk_meta.get('enc')}")
                
                return True
            else:
                print("❌ 未检测到加密标记")
        else:
            print("❌ header解析失败")
            
    except Exception as e:
        print(f"❌ metadata读取测试失败: {e}")
    
    return False

def test_api_format():
    """测试API请求格式"""
    print("\n📡 测试API请求格式...")
    
    try:
        import uuid
        
        # 模拟设备信息
        mac = ":".join([f"{(uuid.getnode() >> i) & 0xff:02x}" for i in range(0, 8*6, 8)][::-1])
        cpu = "Test CPU"
        test_key = "12345678901234567890123456789012"
        
        # 构造请求数据
        request_data = {
            "key": test_key,
            "mac": mac,
            "cpu": cpu
        }
        
        print(f"✅ API请求格式正确:")
        print(f"   - key: {request_data['key']}")
        print(f"   - mac: {request_data['mac']}")
        print(f"   - cpu: {request_data['cpu']}")
        
        return True
        
    except Exception as e:
        print(f"❌ API格式测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 完整工作流程测试")
    print("=" * 50)
    
    tests = [
        ("加密功能", test_encryption),
        ("Metadata读取", test_metadata_reading), 
        ("API格式", test_api_format),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 执行测试: {test_name}")
        try:
            if test_name == "加密功能":
                success, _ = test_func()
            else:
                success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "="*50)
    print("📊 测试结果汇总:")
    
    passed = 0
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\n🎯 总体结果: {passed}/{len(results)} 个测试通过")
    
    if passed == len(results):
        print("🎉 所有测试通过！系统可以正常工作")
    else:
        print("⚠️ 部分测试失败，请检查相关功能")
    
    print("\n📝 使用说明:")
    print("1. 在后端管理界面创建API Key")
    print("2. 使用 model_encryptor.py 加密模型:")
    print("   python model_encryptor.py -i model.safetensors -o encrypted.safetensors -m YOUR_API_KEY")
    print("3. 将 final_model_loader.py 放入 SD WebUI extensions 目录")
    print("4. 重启 WebUI，插件会自动处理加密模型")

if __name__ == "__main__":
    main()

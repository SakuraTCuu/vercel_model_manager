import os
import torch
import uuid
import platform
import subprocess
import requests
import base64
from pathlib import Path
from modules import script_callbacks
import struct

# ========== 直接配置参数 ==========
SERVER_URL = "https://vercel-model-manager.vercel.app/api/verify-key"
API_KEY = "APIKEY_wk_test_model_1_lv3s2cc4"
TIMEOUT = 15
LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "secure_loader.log"))
MODEL_EXTENSIONS = [".safetensors", ".ckpt", ".pt"]

ENCRYPT_FLAG = b'WK_ENCRYPTED_v1'  # 16字节flag

def get_logger():
    import logging
    logger = logging.getLogger("SecureModelLoader")
    logger.setLevel(logging.INFO)
    # 防止重复添加handler
    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
    return logger

def get_device_fingerprint():
    try:
        gpu_info = ""
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_props = torch.cuda.get_device_properties(0)
            gpu_memory_gb = gpu_props.total_memory // (1024**3)
            gpu_info = f"{gpu_name} ({gpu_memory_gb}GB)"
        else:
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if "model name" in line.lower():
                            gpu_info = line.split(":")[1].strip()
                            break
        mac = ":".join([f"{(uuid.getnode() >> i) & 0xff:02x}" for i in range(0, 8*6, 8)][::-1])
        device_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"{gpu_info}-{mac}").hex
        return device_id
    except Exception as e:
        return "unknown_device"

def decode_xor_result(xor_result: str, timestamp: int, logger=None) -> str:
    try:
        decoded_bytes = base64.b64decode(xor_result)
        num_bytes = [
            (timestamp >> 24) & 0xff,
            (timestamp >> 16) & 0xff,
            (timestamp >> 8) & 0xff,
            timestamp & 0xff,
        ]
        decoded_str = ""
        for i, byte in enumerate(decoded_bytes):
            decoded_str += chr(byte ^ num_bytes[i % 4])
        if logger:
            logger.info(f"🔓 解码完成，密钥长度: {len(decoded_str)}")
        return decoded_str
    except Exception as e:
        if logger:
            logger.error(f"❌ 解码异或结果失败: {str(e)}")
        raise ValueError(f"解码失败: {str(e)}")

def read_safetensors_metadata(filepath: str, logger=None):
    try:
        import json
        with open(filepath, mode="rb") as file:
            metadata_len = file.read(8)
            metadata_len = int.from_bytes(metadata_len, "little")
            json_start = file.read(2)
            if metadata_len <= 2 or json_start not in (b'{"', b"{'"):
                if logger:
                    logger.warning(f"⚠️ {filepath} 不是有效的safetensors文件")
                return {}
            json_data = json_start + file.read(metadata_len-2)
            json_obj = json.loads(json_data)
            res = {}
            for k, v in json_obj.get("__metadata__", {}).items():
                res[k] = v
                if isinstance(v, str) and v[0:1] == '{':
                    try:
                        res[k] = json.loads(v)
                    except Exception:
                        pass
            return res
    except Exception as e:
        if logger:
            logger.error(f"❌ 读取safetensors metadata失败: {str(e)}")
        return {}

def is_my_model(filepath: str, logger=None) -> bool:
    try:
        with open(filepath, "rb") as f:
            file_flag = f.read(16)
        if file_flag == ENCRYPT_FLAG:
            if logger:
                logger.info(f"检测到加密flag: {file_flag}")
            return True
        else:
            if logger:
                logger.info(f"未检测到加密flag: {file_flag}")
            return False
    except Exception as e:
        if logger:
            logger.error(f"检测加密flag失败: {str(e)}")
        return False

def request_decryption_key(model_path: str, logger=None) -> str:
    try:
        if logger:
            logger.info(f"🌐 开始向服务器请求解密密钥...")
        if not API_KEY:
            raise ValueError("API密钥未设置，请在config.py中配置API_KEY")
        device_id = get_device_fingerprint()
        mac = ":".join([f"{(uuid.getnode() >> i) & 0xff:02x}" for i in range(0, 8*6, 8)][::-1])
        gpu = "unknown"
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
        if logger:
            logger.info(f"📱 设备ID: {device_id[:16]}...")
            logger.info(f"🔗 MAC地址: {mac}")
            logger.info(f"🎮 GPU信息: {gpu}")
            logger.info(f"📤 发送请求到服务器: {SERVER_URL}")
        response = requests.post(
            SERVER_URL,
            json={
                "key": API_KEY,
                "mac": mac,
                "cpu": gpu
            },
            timeout=TIMEOUT
        )
        response.raise_for_status()
        print("服务器原始响应内容：", response.text)
        if logger:
            logger.info(f"服务器原始响应内容：{response.text}")
        data = response.json()
        if logger:
            logger.info(f"📥 服务器响应: {data}")
        if not data.get("success"):
            error_msg = data.get("error", "Unknown server error")
            if logger:
                logger.error(f"❌ 服务器拒绝请求: {error_msg}")
            raise PermissionError(f"授权失败: {error_msg}")
        xor_result = data.get("xorResult")
        timestamp = data.get("timestamp")
        if not xor_result or not timestamp:
            raise ValueError("服务器响应缺少必要字段")
        if logger:
            logger.info(f"🔐 获取到异或结果: {xor_result[:16]}...")
            logger.info(f"⏰ 时间戳: {timestamp}")
        decryption_key = decode_xor_result(xor_result, timestamp, logger)
        if logger:
            logger.info("✅ 成功获取解密密钥")
        return decryption_key
    except requests.exceptions.RequestException as e:
        if logger:
            logger.error(f"❌ 网络错误: {str(e)}")
        raise ConnectionError(f"无法连接到许可证服务器: {str(e)}")
    except Exception as e:
        if logger:
            logger.error(f"❌ 请求解密密钥失败: {str(e)}")
        raise

def decrypt_model(encrypted_data, key: str, logger=None):
    # 真实解密逻辑（xor为例）
    decrypted = xor_decrypt(encrypted_data, bytes.fromhex(key))
    return decrypted

def xor_decrypt(data, key):
    """XOR解密，与加密同理"""
    return bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])

def print_model_metadata(model_path, logger=None):
    try:
        path = str(model_path)
        if path.endswith('.safetensors'):
            metadata = read_safetensors_metadata(path, logger)
            print(f"【SecureModelLoader】safetensors模型metadata: {metadata}")
            if logger:
                logger.info(f"safetensors模型metadata: {metadata}")
        else:
            model_data = torch.load(path, map_location="cpu")
            if isinstance(model_data, dict):
                metadata = model_data.get('metadata', {})
                print(f"【SecureModelLoader】torch模型metadata: {metadata}")
                if logger:
                    logger.info(f"torch模型metadata: {metadata}")
            else:
                print(f"【SecureModelLoader】模型数据格式异常: {type(model_data)}")
                if logger:
                    logger.warning(f"模型数据格式异常: {type(model_data)}")
    except Exception as e:
        print(f"【SecureModelLoader】读取模型metadata失败: {str(e)}")
        if logger:
            logger.error(f"读取模型metadata失败: {str(e)}")

def decrypt_safetensors_file(enc_path, out_path, key, logger=None):
    """
    解密safetensors加密文件（无flag版）：
    1. 读取头部和metadata
    2. 读取加密tensor数据
    3. xor解密
    4. 还原为原始safetensors文件
    """
    with open(enc_path, "rb") as f:
        header = f.read(8)
        meta_len = int.from_bytes(header, "little")
        metadata = f.read(meta_len)
        encrypted_tensor = f.read()
    decrypted_tensor = xor_decrypt(encrypted_tensor, bytes.fromhex(key))
    # 写回原始safetensors文件
    with open(out_path, "wb") as f:
        f.write(header)
        f.write(metadata)
        f.write(decrypted_tensor)
    if logger:
        logger.info(f"解密完成，输出文件: {out_path}")
    print(f"解密完成，输出文件: {out_path}")

# ========== 模型加载回调 ==========
def on_model_loaded(sd_model):
    logger = get_logger()
    print("【SecureModelLoader】模型加载回调被调用")
    logger.info("【SecureModelLoader】模型加载回调被调用")
    try:
        model_path = getattr(sd_model, 'sd_checkpoint_info', None)
        if model_path is not None and hasattr(model_path, 'filename'):
            model_path = model_path.filename
        else:
            logger.warning("⚠️ 无法获取模型文件路径，跳过自定义校验/解密逻辑")
            print("⚠️ 无法获取模型文件路径，跳过自定义校验/解密逻辑")
            return
        logger.info(f"🔔 检测到模型加载: {model_path}")
        print(f"🔔 检测到模型加载: {model_path}")
        # 判断是否加密（flag）
        if not is_my_model(model_path, logger):
            logger.info(f"🟢 非加密模型，跳过自定义处理: {model_path}")
            print(f"🟢 非加密模型，跳过自定义处理: {model_path}")
            return
        logger.info(f"🔒 检测到加密模型，开始自定义处理: {model_path}")
        print(f"🔒 检测到加密模型，开始自定义处理: {model_path}")
        # ========== 新xor safetensors解密流程 ==========
        with open(model_path, "rb") as f:
            header = f.read(8)
            meta_len = int.from_bytes(header, "little")
            metadata = f.read(meta_len)
            encrypted_tensor = f.read()
        decryption_key = request_decryption_key(model_path, logger)
        decrypted_tensor = xor_decrypt(encrypted_tensor, bytes.fromhex(decryption_key))
        # 校验md5（如果metadata里有model_md5字段）
        import json, hashlib
        try:
            meta_obj = json.loads(metadata)
            md5_expected = meta_obj.get("model_md5", None)
            if md5_expected:
                md5_actual = hashlib.md5(decrypted_tensor).hexdigest()
                if md5_actual == md5_expected:
                    logger.info(f"✅ 解密后模型md5校验通过: {md5_actual}")
                    print(f"✅ 解密后模型md5校验通过: {md5_actual}")
                else:
                    logger.error(f"❌ 解密后模型md5校验失败: {md5_actual} ≠ {md5_expected}")
                    print(f"❌ 解密后模型md5校验失败: {md5_actual} ≠ {md5_expected}")
        except Exception as e:
            logger.warning(f"⚠️ metadata校验异常: {str(e)}")
        logger.info(f"✅ 加密模型处理流程结束: {model_path}")
        print(f"✅ 加密模型处理流程结束: {model_path}")
    except Exception as e:
        logger.error(f"❌ 模型加载回调处理失败: {str(e)}")
        print(f"❌ 模型加载回调处理失败: {str(e)}")

script_callbacks.on_model_loaded(on_model_loaded)
print("🎯 SecureModelLoader 扩展已注册模型加载回调，仅在模型加载时执行自定义逻辑")
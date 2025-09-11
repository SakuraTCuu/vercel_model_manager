"""
final_model_loader.py -- 混合了wk_enc_loader解密逻辑和secure_loader远程密钥管理的模型加载器

功能：
1. 使用wk_enc_loader的判断方法检测加密模型
2. 如果是加密模型，向远程服务器请求解密密钥
3. 使用wk_enc_loader的解密逻辑进行解密
4. 支持多种解密算法

当前状态：解密模块暂未集成密钥，后端需要补充相关逻辑
"""

import io
import os
import json
import struct
import torch
import uuid
import platform
import subprocess
import requests
import base64
from pathlib import Path
import modules.sd_models as sd_models

# ========== 配置参数 ==========
SERVER_URL = "https://vercel-model-manager.vercel.app/api/verify-key"
API_KEY = "APIKEY_wk_test_model_1_lv3s2cc4"
TIMEOUT = 15
LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "final_model_loader.log"))
MODEL_EXTENSIONS = [".safetensors", ".ckpt", ".pt"]

# 配置验证
if not API_KEY or API_KEY == "your-api-key-here":
    print("⚠️ 警告: 请设置有效的API_KEY")

# safetensors import ----------------------------------------------------------
try:
    import safetensors.torch as st
    HAVE_SAFETENSORS = True
except Exception as e:
    print(f"[final-loader] safetensors not available: {e}")
    HAVE_SAFETENSORS = False

META_KEY = "wk_enc"

# -----------------------------------------------------------------------------
# Original loader save
# -----------------------------------------------------------------------------
ORIGINAL_READ_STATE_DICT = getattr(sd_models, "read_state_dict", None)
if ORIGINAL_READ_STATE_DICT is None:
    raise RuntimeError("[final-loader] ERROR: sd_models.read_state_dict not found; plugin cannot install.")

print("[final-loader] Extension loaded. Hooking sd_models.read_state_dict ...")

# ========== 日志系统 ==========
def get_logger():
    import logging
    logger = logging.getLogger("FinalModelLoader")
    logger.setLevel(logging.INFO)
    # 防止重复添加handler
    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
    return logger

# ========== 设备指纹获取 ==========
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

# ========== 远程密钥请求 ==========
def request_decryption_key(model_path: str, logger=None) -> str:
    """
    向远程服务器请求解密密钥
    注意：当前后端暂未实现密钥返回逻辑，此函数为占位实现
    """
    try:
        if logger:
            logger.info("开始向服务器请求解密密钥...")
        
        if not API_KEY:
            raise ValueError("API密钥未设置")
        
        device_id = get_device_fingerprint()
        mac = ":".join([f"{(uuid.getnode() >> i) & 0xff:02x}" for i in range(0, 8*6, 8)][::-1])
        gpu = "unknown"
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
        
        if logger:
            logger.info(f"设备ID: {device_id[:16]}...")
            logger.info(f"MAC地址: {mac}")
            logger.info(f"GPU信息: {gpu}")
            logger.info(f"发送请求到服务器: {SERVER_URL}")
        
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
        
        if logger:
            logger.info(f"服务器原始响应内容：{response.text}")
        
        data = response.json()
        if logger:
            logger.info(f"服务器响应: {data}")
        
        if not data.get("success"):
            error_msg = data.get("error", "Unknown server error")
            if logger:
                logger.error(f"服务器拒绝请求: {error_msg}")
            raise PermissionError(f"授权失败: {error_msg}")
        
        # TODO: 后端需要实现密钥返回逻辑
        # 当前返回占位密钥，实际使用时需要根据后端响应获取真实密钥
        if logger:
            logger.warning("后端暂未实现密钥返回逻辑，使用占位密钥")
        return "00000000000000000000000000000000"  # 32位占位密钥
        
    except requests.exceptions.RequestException as e:
        if logger:
            logger.error(f"网络错误: {str(e)}")
        raise ConnectionError(f"无法连接到许可证服务器: {str(e)}")
    except Exception as e:
        if logger:
            logger.error(f"请求解密密钥失败: {str(e)}")
        raise

# -----------------------------------------------------------------------------
# Helpers (来自wk_enc_loader.py)
# -----------------------------------------------------------------------------
def _get_env_key_or_modelid(meta: dict) -> str:
    """
    Key selection for xor-ascii legacy format.
    1) env WK_XOR_KEY
    2) meta['model_id']
    3) built-in fallback
    """
    k = os.environ.get("WK_XOR_KEY")
    if k:
        k = k.strip()
        print(f"[final-loader] Using env WK_XOR_KEY: {k}")
        return k
    mid = meta.get("model_id")
    if mid:
        print(f"[final-loader] Using model_id as key: {mid}")
        return mid
    k = "wk_default_key_change_me"
    print(f"[final-loader] Using built-in fallback key: {k}")
    return k

def _parse_header(path: str):
    """
    Read safetensors header only. Return (header_len, header_bytes, header_obj) or None.
    """
    try:
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
    except Exception as e:
        print(f"[final-loader] _parse_header fail for {path}: {e}")
        return None

# -----------------------------------------------------------------------------
# Algorithm implementations (来自wk_enc_loader.py)
# -----------------------------------------------------------------------------
def _decrypt_rev_tensor(data: bytes, header_obj: dict) -> bytes:
    """
    Undo per-tensor reverse.
    We reverse each range according to info['data_offsets'].
    """
    out = bytearray(data)  # copy once
    for name, info in header_obj.items():
        if name.startswith("__"):
            continue  # skip metadata keys
        try:
            start, end = info["data_offsets"]
        except Exception:
            continue
        if 0 <= start <= end <= len(out):
            out[start:end] = out[start:end][::-1]
        else:
            print(f"[final-loader] WARN offset out of range for tensor {name}: {start}-{end}/{len(out)}")
    return bytes(out)

def _decrypt_reverse_only(data: bytes) -> bytes:
    return data[::-1]

def _decrypt_xor_ascii(data: bytes, meta: dict) -> bytes:
    key_str = _get_env_key_or_modelid(meta)
    key_bytes = key_str.encode("utf-8")
    klen = len(key_bytes)
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ key_bytes[i % klen]
    return bytes(out)

# TODO: 新增XOR解密函数，使用远程获取的密钥
def _decrypt_xor_with_key(data: bytes, key: str) -> bytes:
    """
    使用远程获取的密钥进行XOR解密
    """
    try:
        # 验证密钥长度
        if len(key) != 32:
            raise ValueError(f"密钥长度必须为32位hex，当前长度: {len(key)}")
        
        # 验证密钥格式
        if not all(c in '0123456789abcdefABCDEF' for c in key):
            raise ValueError("密钥必须为有效的hex字符串")
        
        key_bytes = bytes.fromhex(key)
        out = bytearray(len(data))
        for i, b in enumerate(data):
            out[i] = b ^ key_bytes[i % len(key_bytes)]
        return bytes(out)
    except Exception as e:
        print(f"[final-loader] XOR解密失败: {e}")
        raise

# -----------------------------------------------------------------------------
# Core decrypt of file -> full safetensors bytes
# -----------------------------------------------------------------------------
def _decrypt_safetensors_file(path: str, alg: str, meta: dict,
                              header_len: int, header_bytes: bytes, header_obj: dict, 
                              remote_key: str = None) -> bytes:
    """
    Read encrypted file's data block, decrypt by alg, return full safetensors bytes (header+data).
    新增remote_key参数，用于远程密钥解密
    """
    with open(path, "rb") as f:
        f.seek(8 + header_len)
        data_enc = f.read()

    if alg == "rev-tensor":
        print(f"[final-loader] decrypt alg=rev-tensor (per tensor)...")
        data_dec = _decrypt_rev_tensor(data_enc, header_obj)
    elif alg == "reverse-only":
        print(f"[final-loader] decrypt alg=reverse-only (whole block)...")
        data_dec = _decrypt_reverse_only(data_enc)
    elif alg == "xor-ascii":
        print(f"[final-loader] decrypt alg=xor-ascii (whole block)...")
        data_dec = _decrypt_xor_ascii(data_enc, meta)
    elif alg == "xor-remote" and remote_key:
        print(f"[final-loader] decrypt alg=xor-remote (with remote key)...")
        data_dec = _decrypt_xor_with_key(data_enc, remote_key)
    else:
        raise RuntimeError(f"[final-loader] Unknown wk_enc alg: {alg}")

    full_bytes = struct.pack("<Q", len(header_bytes)) + header_bytes + data_dec
    return full_bytes

# -----------------------------------------------------------------------------
# Load safetensors from in-memory bytes
# -----------------------------------------------------------------------------
def _load_safetensors_from_bytes(data: bytes):
    try:
        return st.load(data)
    except Exception as e:
        print(f"[final-loader] st.load(bytes) failed: {e}")
        raise

# -----------------------------------------------------------------------------
# Hook: read_state_dict (混合逻辑)
# -----------------------------------------------------------------------------
def final_read_state_dict(checkpoint_file, print_global_state=False, map_location=None):
    logger = get_logger()  # 只获取一次logger
    print(f"[final-loader] >>> final_read_state_dict: {checkpoint_file}")
    logger.info(f"开始处理模型: {checkpoint_file}")
    
    low = checkpoint_file.lower()

    if HAVE_SAFETENSORS and low.endswith(".safetensors"):
        logger.info("检测到safetensors文件，开始解析头部")
        parsed = _parse_header(checkpoint_file)
        
        if parsed is not None:
            header_len, header_bytes, header_obj = parsed
            logger.info("头部解析成功，检查加密标记")
            
            meta_root = header_obj.get("__metadata__", {})
            wk_meta = meta_root.get(META_KEY)
            
            if isinstance(wk_meta, str):
                try:
                    wk_meta = json.loads(wk_meta)
                except Exception as e:
                    logger.error(f"wk_meta json解码失败: {e}")
                    wk_meta = None

            if wk_meta and wk_meta.get("enc"):
                alg = wk_meta.get("alg", "?")
                logger.info(f"检测到加密模型，算法: {alg}")
                print(f"[final-loader] encrypted safetensors detected: alg={alg}")
                
                try:
                    # 如果是加密模型，请求远程密钥
                    logger.info("开始请求远程解密密钥")
                    
                    remote_key = request_decryption_key(checkpoint_file, logger)
                    logger.info("成功获取远程解密密钥")
                    
                    # 使用wk_enc_loader的解密逻辑
                    logger.info("开始解密模型数据")
                    full_bytes = _decrypt_safetensors_file(
                        checkpoint_file, alg, wk_meta,
                        header_len, header_bytes, header_obj,
                        remote_key
                    )
                    
                    logger.info("模型解密成功，开始加载")
                    sd = _load_safetensors_from_bytes(full_bytes)
                    logger.info("模型加载成功，返回解密后的state_dict")
                    print("[final-loader] returning decrypted state_dict.")
                    return sd
                    
                except Exception as e:
                    logger.error(f"解密/加载失败: {str(e)}")
                    print(f"[final-loader] ERROR decrypt/load: {e}")
                    # raise here so A1111 doesn't try to parse encrypted bytes
                    raise
        else:
            logger.warning("头部解析失败，使用原始加载器")
    else:
        logger.info("非safetensors文件，使用原始加载器")

    # fallback normal loader
    logger.info("使用原始加载器")
    return ORIGINAL_READ_STATE_DICT(
        checkpoint_file,
        print_global_state=print_global_state,
        map_location=map_location
    )

# -----------------------------------------------------------------------------
# Install hook
# -----------------------------------------------------------------------------
sd_models.read_state_dict = final_read_state_dict
print("[final-loader] sd_models.read_state_dict successfully hooked (final_model_loader).")
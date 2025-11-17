# 这是你原有的SD扩展代码，只需要做少量适配
import io
import os
import json
import struct
import time
import torch
import uuid
import platform
import subprocess
import requests
import base64
from pathlib import Path

# ========== 配置参数 ==========
SERVER_URL = os.environ.get("WK_SERVER_URL", "https://vercel-model-manager.vercel.app/api/verify-key")
TIMEOUT = int(os.environ.get("WK_TIMEOUT", "15"))
RETRIES = int(os.environ.get("WK_RETRIES", "2"))
RETRY_BACKOFF = float(os.environ.get("WK_RETRY_BACKOFF", "1.5"))
LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "final_model_loader.log"))
MODEL_EXTENSIONS = [".safetensors", ".ckpt", ".pt"]
UI_NOTIFY = os.environ.get("WK_UI_NOTIFY", "1") in ("1", "true", "True")

# safetensors import ----------------------------------------------------------
try:
    import safetensors.torch as st
    HAVE_SAFETENSORS = True
except Exception as e:
    print(f"[final-loader] safetensors not available: {e}")
    HAVE_SAFETENSORS = False

META_KEY = "wk_enc"

# ========== 新增函数：供 prestartup_script 调用 ==========
def detect_encrypted_model(checkpoint_path):
    """
    检测模型是否加密 - 供外部调用
    返回: (is_encrypted, parsed_data)
    """
    low = checkpoint_path.lower()
    
    if HAVE_SAFETENSORS and low.endswith(".safetensors"):
        parsed = _parse_header(checkpoint_path)
        
        if parsed is not None:
            header_len, header_bytes, header_obj = parsed
            meta_root = header_obj.get("__metadata__", {})
            wk_meta = meta_root.get(META_KEY)
            
            if isinstance(wk_meta, str):
                try:
                    wk_meta = json.loads(wk_meta)
                except Exception as e:
                    print(f"[final-loader] wk_meta json解码失败: {e}")
                    wk_meta = None

            if wk_meta and wk_meta.get("enc"):
                return True, {
                    "header_len": header_len,
                    "header_bytes": header_bytes, 
                    "header_obj": header_obj,
                    "wk_meta": wk_meta
                }
    
    return False, None

# ========== 你原有的所有函数保持不变 ==========
# 包括：get_logger, notify_console, get_device_fingerprint, 
# request_decryption_key, _get_env_key_or_modelid, _parse_header,
# _decrypt_rev_tensor, _decrypt_reverse_only, _decrypt_xor_ascii,
# _decrypt_xor_with_key, _decrypt_xor_with_bytes, 
# _decrypt_safetensors_file, _load_safetensors_from_bytes

def get_logger():
    import logging
    logger = logging.getLogger("FinalModelLoader")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
    return logger

def notify_console(message: str):
    try:
        print(f"[final-loader] {message}")
    except Exception:
        pass

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

def request_decryption_key(model_id: str, logger=None) -> dict:
    # 你原有的 request_decryption_key 函数完整内容
    try:
        if logger:
            logger.info(f"开始向服务器请求解密密钥，model_id: {model_id}")
        
        if not model_id:
            raise ValueError("model_id未设置")
        
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
        
        attempt = 0
        delay = 1.0
        response = None
        while True:
            try:
                if logger:
                    logger.info(f"请求授权（第 {attempt+1} 次） -> {SERVER_URL}")
                response = requests.post(
                    SERVER_URL,
                    json={
                        "key": model_id,
                        "mac": mac,
                        "cpu": gpu
                    },
                    timeout=TIMEOUT
                )
                response.raise_for_status()
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as net_ex:
                if attempt >= RETRIES:
                    if logger:
                        logger.error(f"网络重试已耗尽: {net_ex}")
                    raise ConnectionError(f"无法连接到许可证服务器: {net_ex}")
                if logger:
                    logger.warning(f"网络问题（{type(net_ex).__name__}），将在 {delay:.1f}s 后重试: {net_ex}")
                time.sleep(delay)
                delay *= RETRY_BACKOFF
                attempt += 1
            except requests.exceptions.RequestException as other_ex:
                if logger:
                    logger.error(f"请求失败，不重试: {other_ex}")
                raise
        
        if logger:
            logger.info(f"服务器原始响应内容：{response.text}")
        
        data = response.json()
        if logger:
            logger.info(f"服务器响应: {data}")
        
        code = data.get("code", 0)
        msg = data.get("msg", "")
        id_value = data.get("id", "")
        timestamp = data.get("timestamp", 0)
        
        if code == 0:
            error_msg = msg if msg else "Unknown server error"
            if logger:
                logger.error(f"服务器拒绝请求(不重试): {error_msg}")
            print(f"[final-loader] ⚠️ 模型授权失败: {error_msg}")
            print(f"[final-loader] 请检查model_id '{model_id}' 是否在后端数据库中已创建且状态为启用")
            return None
        
        if code == 1:
            if logger:
                logger.info(f"验证成功: {msg}")
            if not id_value:
                raise ValueError("服务器返回成功但缺少解密密钥(id字段)")
            if not timestamp:
                raise ValueError("服务器返回成功但缺少时间戳(timestamp字段)")
            return {
                "success": True,
                "xorResult": id_value,
                "timestamp": timestamp
            }
        
        raise ValueError(f"未知的返回code: {code}")
        
    except requests.exceptions.RequestException as e:
        if logger:
            logger.error(f"网络错误: {str(e)}")
        raise ConnectionError(f"无法连接到许可证服务器: {str(e)}")
    except Exception as e:
        if logger:
            logger.error(f"请求解密密钥失败: {str(e)}")
        raise

def _get_env_key_or_modelid(meta: dict) -> str:
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

def _decrypt_rev_tensor(data: bytes, header_obj: dict) -> bytes:
    out = bytearray(data)
    for name, info in header_obj.items():
        if name.startswith("__"):
            continue
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

def _decrypt_xor_with_key(data: bytes, key: str) -> bytes:
    try:
        if len(key) != 32:
            raise ValueError(f"密钥长度必须为32位hex，当前长度: {len(key)}")
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

def _decrypt_xor_with_bytes(data: bytes, key_bytes: bytes) -> bytes:
    try:
        out = bytearray(len(data))
        for i, b in enumerate(data):
            out[i] = b ^ key_bytes[i % len(key_bytes)]
        return bytes(out)
    except Exception as e:
        print(f"[final-loader] XOR字节解密失败: {e}")
        raise

def _decrypt_safetensors_file(path: str, alg: str, meta: dict,
                              header_len: int, header_bytes: bytes, header_obj: dict, 
                              decrypt_info: dict = None) -> bytes:
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
    elif alg == "xor-remote" and decrypt_info:
        print(f"[final-loader] decrypt alg=xor-remote (with remote key)...")
        xor_result = decrypt_info.get("xorResult", "")
        if not xor_result:
            raise ValueError("远程解密信息缺少xorResult")
        try:
            key_bytes = base64.b64decode(xor_result)
            data_dec = _decrypt_xor_with_bytes(data_enc, key_bytes)
        except Exception as e:
            raise ValueError(f"解析远程密钥失败: {e}")
    else:
        print(f"[final-loader] Unknown/unsupported alg: {alg}, trying rev-tensor as fallback...")
        data_dec = _decrypt_rev_tensor(data_enc, header_obj)

    full_bytes = struct.pack("<Q", len(header_bytes)) + header_bytes + data_dec
    return full_bytes

def _load_safetensors_from_bytes(data: bytes):
    try:
        return st.load(data)
    except Exception as e:
        print(f"[final-loader] st.load(bytes) failed: {e}")
        raise

def final_read_state_dict(checkpoint_file, print_global_state=False, map_location=None):
    """
    你原有的 final_read_state_dict 函数
    为了兼容性，保持参数不变，但在 ComfyUI 中 map_location 参数可能不会被使用
    """
    logger = get_logger()
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
                model_id = wk_meta.get("model_id")
                
                if not model_id:
                    logger.error("加密模型缺少model_id")
                    raise ValueError("加密模型缺少model_id")
                
                logger.info(f"检测到加密模型，算法: {alg}, model_id: {model_id}")
                print(f"[final-loader] encrypted safetensors detected: alg={alg}, model_id={model_id}")
                
                try:
                    logger.info(f"开始使用model_id请求远程解密密钥: {model_id}")
                    decrypt_info = request_decryption_key(model_id, logger)
                    
                    if decrypt_info is None:
                        error_msg = f"授权失败: 无法获取解密密钥，model_id '{model_id}' 可能未创建或已停用"
                        logger.error(error_msg)
                        notify_console(error_msg)
                        if UI_NOTIFY:
                            raise RuntimeError(error_msg)
                        return None
                    
                    logger.info("成功获取远程解密密钥")
                    logger.info("开始解密模型数据")
                    full_bytes = _decrypt_safetensors_file(
                        checkpoint_file, alg, wk_meta,
                        header_len, header_bytes, header_obj,
                        decrypt_info
                    )
                    
                    logger.info("模型解密成功，开始加载")
                    sd = _load_safetensors_from_bytes(full_bytes)
                    logger.info("模型加载成功，返回解密后的state_dict")
                    print("[final-loader] returning decrypted state_dict.")
                    return sd
                    
                except Exception as e:
                    logger.error(f"解密/加载失败: {str(e)}")
                    notify_console(f"解密失败: {e}")
                    if UI_NOTIFY:
                        raise
                    return None
        else:
            logger.warning("头部解析失败，使用原始加载器")
    else:
        logger.info("非safetensors文件，使用原始加载器")

    # 在 ComfyUI 中，我们需要回退到原始加载器
    # 注意：这里需要适配 ComfyUI 的原始加载器
    logger.info("使用原始加载器")
    
    # 由于我们在 ComfyUI 环境中，需要调用 ComfyUI 的加载逻辑
    # 这里暂时返回 None，由上层处理
    return None
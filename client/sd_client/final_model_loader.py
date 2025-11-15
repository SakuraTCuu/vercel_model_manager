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
import time
import torch
import uuid
import platform
import subprocess
import requests
import base64
from pathlib import Path
import modules.sd_models as sd_models

# ========== 配置参数 ==========
# 支持通过环境变量覆盖，便于本地联调/网络加速
SERVER_URL = os.environ.get("WK_SERVER_URL", "https://vercel-model-manager.vercel.app/api/verify-key")
TIMEOUT = int(os.environ.get("WK_TIMEOUT", "15"))
RETRIES = int(os.environ.get("WK_RETRIES", "2"))  # 额外重试次数（不含首次）
RETRY_BACKOFF = float(os.environ.get("WK_RETRY_BACKOFF", "1.5"))  # 退避倍数
LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "final_model_loader.log"))
MODEL_EXTENSIONS = [".safetensors", ".ckpt", ".pt"]
UI_NOTIFY = os.environ.get("WK_UI_NOTIFY", "1") in ("1", "true", "True")  # 控制是否在SD界面抛错提示
PENDING_UI_LOGS = []  # shared.log 未就绪时临时缓存

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

# Hook safetensors库本身，确保LoRAs等也能被处理
ORIGINAL_LOAD_FILE = None
if HAVE_SAFETENSORS:
    ORIGINAL_LOAD_FILE = getattr(st, "load_file", None)

print("[final-loader] Extension loaded. Hooking sd_models.read_state_dict and safetensors.torch.load_file ...")

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

# ========== UI 提示封装 ==========
def notify_ui(message: str):
    """尝试通过 stable-diffusion-webui 的 shared.log（若存在）向前端展示，失败则仅打印。"""
    # 1) 优先尝试使用 Gradio 的内置提示（左上角临时提示框）
    try:
        import gradio as gr
        try:
            gr.Info(message)
        except Exception:
            pass
    except Exception:
        pass

    # 2) 回退到 shared.log 列表（若存在）
    try:
        import modules.shared as shared
        if hasattr(shared, 'log') and isinstance(shared.log, list):
            shared.log.append(f"[授权] {message}")
            # 若之前有缓存，尝试一次性刷新并清空
            if PENDING_UI_LOGS:
                for m in PENDING_UI_LOGS:
                    shared.log.append(f"[授权] {m}")
                PENDING_UI_LOGS.clear()
        else:
            # log结构尚未就绪，加入缓存
            PENDING_UI_LOGS.append(message)
    except Exception:
        # shared模块尚未可用，加入缓存
        PENDING_UI_LOGS.append(message)
    print(f"[final-loader][UI] {message}")

def _flush_pending_ui_logs():
    """尝试刷新缓存的UI日志到shared.log, 在脚本末尾调用一次。"""
    if not PENDING_UI_LOGS:
        return
    try:
        import modules.shared as shared
        if hasattr(shared, 'log') and isinstance(shared.log, list):
            for m in PENDING_UI_LOGS:
                shared.log.append(f"[授权] {m}")
            PENDING_UI_LOGS.clear()
    except Exception:
        # 仍不可用则忽略，后续notify_ui再次调用时会再尝试
        pass

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
def request_decryption_key(model_id: str, logger=None) -> dict:

    # return {
    #     "success": True,
    #     "xorResult": "id_value",
    #     "timestamp": "1122232424"
    # }
    """
    向远程服务器请求解密密钥
    使用从模型metadata中读取的model_id（实际就是api_key）进行验证
    """
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
        
        # 仅在网络超时/连接错误时重试；业务逻辑错误不重试
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
                break  # 成功拿到响应，无需重试
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as net_ex:
                # 仅对可恢复的网络错误按 RETRIES 尝试
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
                # 其他请求异常（如 HTTP 错误码），不做重试，直接抛出
                if logger:
                    logger.error(f"请求失败，不重试: {other_ex}")
                raise
        
        if logger:
            logger.info(f"服务器原始响应内容：{response.text}")
        
        data = response.json()
        if logger:
            logger.info(f"服务器响应: {data}")
        
        # 检查统一返回格式
        code = data.get("code", 0)
        msg = data.get("msg", "")
        id_value = data.get("id", "")
        timestamp = data.get("timestamp", 0)
        
        if code == 0:
            # 业务逻辑失败：不重试
            error_msg = msg if msg else "Unknown server error"
            if logger:
                logger.error(f"服务器拒绝请求(不重试): {error_msg}")
            print(f"[final-loader] ⚠️ 模型授权失败: {error_msg}")
            print(f"[final-loader] 请检查model_id '{model_id}' 是否在后端数据库中已创建且状态为启用")
            return None
        
        # 成功情况
        if code == 1:
            if logger:
                logger.info(f"验证成功: {msg}")
            if not id_value:
                raise ValueError("服务器返回成功但缺少解密密钥(id字段)")
            if not timestamp:
                raise ValueError("服务器返回成功但缺少时间戳(timestamp字段)")
            # 返回解密信息，id字段包含xorResult
            return {
                "success": True,
                "xorResult": id_value,
                "timestamp": timestamp
            }
        
        # 未知的code值
        raise ValueError(f"未知的返回code: {code}")
        
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

def _decrypt_xor_with_bytes(data: bytes, key_bytes: bytes) -> bytes:
    """
    使用字节密钥进行XOR解密
    """
    try:
        out = bytearray(len(data))
        for i, b in enumerate(data):
            out[i] = b ^ key_bytes[i % len(key_bytes)]
        return bytes(out)
    except Exception as e:
        print(f"[final-loader] XOR字节解密失败: {e}")
        raise

# -----------------------------------------------------------------------------
# Core decrypt of file -> full safetensors bytes
# -----------------------------------------------------------------------------
def _decrypt_safetensors_file(path: str, alg: str, meta: dict,
                              header_len: int, header_bytes: bytes, header_obj: dict, 
                              decrypt_info: dict = None) -> bytes:
    """
    Read encrypted file's data block, decrypt by alg, return full safetensors bytes (header+data).
    decrypt_info: 从后端返回的解密信息 {"xorResult": str, "timestamp": int}
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
    elif alg == "xor-remote" and decrypt_info:
        print(f"[final-loader] decrypt alg=xor-remote (with remote key)...")
        xor_result = decrypt_info.get("xorResult", "")
        if not xor_result:
            raise ValueError("远程解密信息缺少xorResult")
        # 将base64编码的xorResult解码为密钥
        try:
            key_bytes = base64.b64decode(xor_result)
            data_dec = _decrypt_xor_with_bytes(data_enc, key_bytes)
        except Exception as e:
            raise ValueError(f"解析远程密钥失败: {e}")
    else:
        # 对于不认识的算法或缺少解密信息，尝试使用rev-tensor作为默认
        print(f"[final-loader] Unknown/unsupported alg: {alg}, trying rev-tensor as fallback...")
        data_dec = _decrypt_rev_tensor(data_enc, header_obj)

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
                model_id = wk_meta.get("model_id")  # 从metadata中读取model_id
                
                if not model_id:
                    logger.error("加密模型缺少model_id")
                    raise ValueError("加密模型缺少model_id")
                
                logger.info(f"检测到加密模型，算法: {alg}, model_id: {model_id}")
                print(f"[final-loader] encrypted safetensors detected: alg={alg}, model_id={model_id}")
                
                try:
                    # 使用从模型metadata读取的model_id请求远程密钥
                    logger.info(f"开始使用model_id请求远程解密密钥: {model_id}")
                    
                    decrypt_info = request_decryption_key(model_id, logger)
                    
                    # 检查是否获取到解密信息
                    if decrypt_info is None:
                        error_msg = f"授权失败: 无法获取解密密钥，model_id '{model_id}' 可能未创建或已停用"
                        logger.error(error_msg)
                        notify_ui(error_msg)
                        if UI_NOTIFY:
                            # 抛出异常以便在SD界面右上角显示红色错误
                            raise RuntimeError(error_msg)
                        return None
                    
                    logger.info("成功获取远程解密密钥")
                    
                    # 使用wk_enc_loader的解密逻辑
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
                    notify_ui(f"解密失败: {e}")
                    if UI_NOTIFY:
                        raise
                    return None
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
# Hook: safetensors.torch.load_file (用于LoRAs等)
# -----------------------------------------------------------------------------
def final_load_file(filename, device="cpu"):
    """
    Hook safetensors.torch.load_file，确保LoRAs等也能被处理
    """
    logger = get_logger()
    print(f"[wkkkkklora] >>> final_load_file: {filename}")
    logger.info(f"开始处理safetensors文件: {filename}")
    
    low = filename.lower()
    
    if low.endswith(".safetensors"):
        logger.info("检测到safetensors文件，开始解析头部")
        parsed = _parse_header(filename)
        
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
                    # 使用从模型metadata读取的model_id请求远程密钥
                    logger.info(f"开始使用model_id请求远程解密密钥: {model_id}")
                    
                    decrypt_info = request_decryption_key(model_id, logger)
                    
                    # 检查是否获取到解密信息
                    if decrypt_info is None:
                        error_msg = f"授权失败: 无法获取解密密钥，model_id '{model_id}' 可能未创建或已停用"
                        logger.error(error_msg)
                        notify_ui(error_msg)
                        if UI_NOTIFY:
                            raise RuntimeError(error_msg)
                        return None
                    
                    logger.info("成功获取远程解密密钥")
                    
                    # 使用wk_enc_loader的解密逻辑
                    logger.info("开始解密模型数据")
                    full_bytes = _decrypt_safetensors_file(
                        filename, alg, wk_meta,
                        header_len, header_bytes, header_obj,
                        decrypt_info
                    )
                    
                    logger.info("模型解密成功，开始加载")
                    sd = _load_safetensors_from_bytes(full_bytes)
                    logger.info("模型加载成功，返回解密后的state_dict")
                    print("[final-loader] returning decrypted state_dict from load_file.")
                    return sd
                    
                except Exception as e:
                    logger.error(f"解密/加载失败: {str(e)}")
                    notify_ui(f"解密失败: {e}")
                    if UI_NOTIFY:
                        raise
                    return None
        else:
            logger.warning("头部解析失败，使用原始加载器")
    else:
        logger.info("非safetensors文件，使用原始加载器")

    # fallback normal loader
    if ORIGINAL_LOAD_FILE:
        logger.info("使用原始safetensors加载器")
        return ORIGINAL_LOAD_FILE(filename, device=device)
    else:
        raise RuntimeError("[final-loader] ORIGINAL_LOAD_FILE not available")

# -----------------------------------------------------------------------------
# Install hooks
# -----------------------------------------------------------------------------
sd_models.read_state_dict = final_read_state_dict
print("[final-loader] sd_models.read_state_dict successfully hooked (final_model_loader).")

if HAVE_SAFETENSORS and ORIGINAL_LOAD_FILE:
    st.load_file = final_load_file
    print("[wkkkkk] safetensors.torch.load_file successfully hooked (final_model_loader).")

# 尝试在脚本加载完成时刷新可能在早期阶段积累的缓存消息
_flush_pending_ui_logs()
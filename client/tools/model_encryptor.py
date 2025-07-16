# -*- coding: utf-8 -*-
import os
import sys
import hashlib
import json
import secrets
import time
import argparse
import uuid
import struct

# ========== 配置 ========== #
API_URL = "http://localhost:3000/api/model-encrypt-register"  # 后台注册接口

# ========== 工具函数 ========== #
def random_key(length=32):
    return secrets.token_hex(length)

def calc_md5(filepath):
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def xor_encrypt(data, key):
    return bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])

# ========== 主流程 ========== #
def encrypt_safetensors(model_path, output_path, meta=None, custom_key=None):
    """
    safetensors加密：完全不动头和metadata，只加密tensor数据部分，文件尾部追加b'wks'标记
    """
    if custom_key:
        if len(custom_key) != 32:
            print("自定义key必须是32位hex字符串（16字节）")
            sys.exit(1)
        encrypt_key = custom_key
    else:
        encrypt_key = random_key(16)  # 32 hex chars = 16 bytes
    key_bytes = bytes.fromhex(encrypt_key)
    with open(model_path, "rb") as f:
        header = f.read(8)
        meta_len = int.from_bytes(header, "little")
        metadata = f.read(meta_len)
        tensor_data = f.read()
    encrypted_tensor = xor_encrypt(tensor_data, key_bytes)
    out_file = os.path.join(output_path, os.path.basename(model_path))
    with open(out_file, "wb") as f:
        f.write(header)
        f.write(metadata)
        f.write(encrypted_tensor)
        # f.write(b'wks')  # 文件尾部追加flag
    return encrypt_key, encrypt_key, None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path")
    parser.add_argument("output_path")
    parser.add_argument("--key", type=str, help="自定义32位hex key（仅xor模式）")
    args = parser.parse_args()

    model_path = args.model_path
    output_path = args.output_path
    custom_key = args.key

    encrypt_key, decrypt_key, _, _ = encrypt_safetensors(model_path, output_path, custom_key=custom_key)
    print(f"加密完成！加密key: {encrypt_key}\n解密key: {decrypt_key}")

if __name__ == "__main__":
    main()

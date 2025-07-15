# -*- coding: utf-8 -*-
import os
import sys
import hashlib
import json
import secrets
import urllib.request
import urllib.parse
from base64 import b64encode, b64decode
import time
import argparse
import uuid

# ========== 新增依赖 ========== #
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("请先安装依赖: pip install cryptography")
    sys.exit(1)

# ========== 配置 ========== #
API_URL = "http://localhost:3000/api/model-encrypt-register"  # 后台注册接口
RSA_PUBLIC_KEY_PATH = "model_public_key.pem"
RSA_PRIVATE_KEY_PATH = "model_private_key.pem"

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

# ========== RSA密钥管理 ========== #
def generate_rsa_keypair(pub_path=RSA_PUBLIC_KEY_PATH, priv_path=RSA_PRIVATE_KEY_PATH, key_size=2048):
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )
    public_key = private_key.public_key()
    with open(priv_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    with open(pub_path, "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    print(f"RSA密钥对已生成: {pub_path}, {priv_path}")

def load_rsa_public_key(pub_path=RSA_PUBLIC_KEY_PATH):
    with open(pub_path, "rb") as f:
        return serialization.load_pem_public_key(f.read(), backend=default_backend())

def load_rsa_private_key(priv_path=RSA_PRIVATE_KEY_PATH):
    with open(priv_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

# ========== AES加密大文件 ========== #
def aes_encrypt_file(input_path, output_path, key, iv=None, chunk_size=1024*1024):
    if iv is None:
        iv = secrets.token_bytes(16)
    cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
        fout.write(iv)  # 文件头写入IV
        while True:
            chunk = fin.read(chunk_size)
            if not chunk:
                break
            enc_chunk = encryptor.update(chunk)
            fout.write(enc_chunk)
        fout.write(encryptor.finalize())
    return iv

def aes_decrypt_file(input_path, output_path, key, chunk_size=1024*1024):
    with open(input_path, "rb") as fin:
        iv = fin.read(16)
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        with open(output_path, "wb") as fout:
            while True:
                chunk = fin.read(chunk_size)
                if not chunk:
                    break
                dec_chunk = decryptor.update(chunk)
                fout.write(dec_chunk)
            fout.write(decryptor.finalize())

# ========== 主流程 ========== #
ENCRYPT_FLAG = b'WK_ENCRYPTED_v1'  # 16字节flag
def encrypt_safetensors(model_path, output_path, meta=None, mode="hybrid"):
    """
    加密 safetensors 文件，支持xor和hybrid（AES+RSA）模式
    返回 (加密key, 解密key, 加密后文件md5, 元数据)
    """
    if mode == "xor":
        # 兼容原有xor逻辑
        encrypt_key = random_key(16)  # 32 hex chars = 16 bytes
        key_bytes = bytes.fromhex(encrypt_key)
        with open(model_path, "rb") as f:
            data = f.read()
        encrypted = xor_encrypt(data, key_bytes)
        metadata = {
            "is_wk_encrypt": True,
            "author": "wks",
            "time": int(time.time()),
            "model_md5": hashlib.md5(data).hexdigest(),
        }
        encrypted_with_meta = ENCRYPT_FLAG + encrypted + b"\n__META__" + json.dumps(metadata, ensure_ascii=False).encode("utf-8")
        out_file = os.path.join(output_path, os.path.basename(model_path))
        with open(out_file, "wb") as f:
            f.write(encrypted_with_meta)
        return encrypt_key, encrypt_key, None, metadata
    elif mode == "hybrid":
        # 混合加密：AES加密大文件，RSA加密AES密钥
        aes_key = secrets.token_bytes(32)  # 256位
        if not os.path.exists(RSA_PUBLIC_KEY_PATH):
            print("未找到RSA公钥，自动生成...")
            generate_rsa_keypair()
        public_key = load_rsa_public_key()
        encrypted_aes_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        out_file = os.path.join(output_path, os.path.basename(model_path) + ".enc")
        iv = aes_encrypt_file(model_path, out_file, aes_key)
        model_md5 = calc_md5(model_path)
        metadata = {
            "is_wk_encrypt": True,
            "author": "wks",
            "time": int(time.time()),
            "model_md5": model_md5,
            "mode": "hybrid",
            "aes_key_rsa": b64encode(encrypted_aes_key).decode(),
            "iv": b64encode(iv).decode(),
            "rsa_pubkey": RSA_PUBLIC_KEY_PATH,
        }
        # 先写flag，再写加密内容和元数据
        with open(out_file, "rb") as f:
            enc_content = f.read()
        with open(out_file, "wb") as f:
            f.write(ENCRYPT_FLAG + enc_content)
        with open(out_file, "ab") as f:
            f.write(b"\n__META__" + json.dumps(metadata, ensure_ascii=False).encode("utf-8"))
        return b64encode(encrypted_aes_key).decode(), None, None, metadata
    else:
        raise ValueError("不支持的加密模式: {}".format(mode))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_path")
    parser.add_argument("output_path")
    parser.add_argument("mode", nargs="?", default="xor")
    parser.add_argument("--key", type=str, help="自定义32位hex key（仅xor模式）")
    args = parser.parse_args()

    model_path = args.model_path
    output_path = args.output_path
    mode = args.mode
    custom_key = args.key

    if mode == "xor":
        if custom_key:
            if len(custom_key) != 32:
                print("自定义key必须是32位hex字符串（16字节）")
                sys.exit(1)
            encrypt_key = custom_key
        else:
            # 自动生成32位uuid（不带-，hex字符串）
            encrypt_key = uuid.uuid4().hex
        decrypt_key = encrypt_key
        key_bytes = bytes.fromhex(encrypt_key)
        with open(model_path, "rb") as f:
            data = f.read()
        encrypted = xor_encrypt(data, key_bytes)
        metadata = {
            "is_wk_encrypt": True,
            "author": "wks",
            "time": int(time.time()),
            "model_md5": hashlib.md5(data).hexdigest(),
        }
        encrypted_with_meta = ENCRYPT_FLAG + encrypted + b"\n__META__" + json.dumps(metadata, ensure_ascii=False).encode("utf-8")
        out_file = os.path.join(output_path, os.path.basename(model_path))
        with open(out_file, "wb") as f:
            f.write(encrypted_with_meta)
        print(f"加密完成！加密key: {encrypt_key}\n解密key: {decrypt_key}")
        print(f"元数据: {json.dumps(metadata, ensure_ascii=False, indent=2)}")
        print("如需生成/更换RSA密钥对，请运行: python -c 'import tools.model_encryptor as m; m.generate_rsa_keypair()'")
        return
    # hybrid模式保持原逻辑
    encrypt_key, decrypt_key, _, meta = encrypt_safetensors(model_path, output_path, mode=mode)
    print(f"加密完成！加密key: {encrypt_key}\n解密key: {decrypt_key}")
    print(f"元数据: {json.dumps(meta, ensure_ascii=False, indent=2)}")
    print("如需生成/更换RSA密钥对，请运行: python -c 'import tools.model_encryptor as m; m.generate_rsa_keypair()'")

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
import os
import sys
import json
import hashlib
from base64 import b64decode

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("请先安装依赖: pip install cryptography")
    sys.exit(1)

RSA_PRIVATE_KEY_PATH = "model_private_key.pem"
ENCRYPT_FLAG = b'WK_ENCRYPTED_v1'  # 16字节flag

# ========== 工具函数 ========== #
def xor_decrypt(data, key):
    return bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])

def load_rsa_private_key(priv_path=RSA_PRIVATE_KEY_PATH):
    with open(priv_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

def aes_decrypt_file(input_path, output_path, key, iv, meta_len, chunk_size=1024*1024):
    with open(input_path, "rb") as fin:
        # 读取除去元数据的部分
        file_size = os.path.getsize(input_path)
        data_len = file_size - meta_len
        iv = b64decode(iv) if isinstance(iv, str) else iv
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        with open(output_path, "wb") as fout:
            read_bytes = 0
            while read_bytes < data_len:
                to_read = min(chunk_size, data_len - read_bytes)
                chunk = fin.read(to_read)
                if not chunk:
                    break
                dec_chunk = decryptor.update(chunk)
                fout.write(dec_chunk)
                read_bytes += len(chunk)
            fout.write(decryptor.finalize())

# ========== 主流程 ========== #
def extract_meta_from_file(enc_path):
    """
    从加密文件末尾提取元数据和加密内容长度
    返回 (meta_dict, meta_len)
    """
    with open(enc_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        filesize = f.tell()
        # 读取最后4KB查找__META__标记
        read_size = min(4096, filesize)
        f.seek(-read_size, os.SEEK_END)
        tail = f.read(read_size)
        idx = tail.rfind(b"__META__")
        if idx == -1:
            raise ValueError("未找到元数据标记 __META__，无法解密")
        meta_start = filesize - read_size + idx + len(b"__META__")
        f.seek(meta_start)
        meta_bytes = f.read()
        meta_str = meta_bytes.decode("utf-8")
        meta = json.loads(meta_str)
        meta_len = len(meta_bytes) + idx + len(b"__META__")
        return meta, meta_len

def main():
    if len(sys.argv) < 3:
        print("用法: python model_decryptor.py <加密文件路径> <输出目录> [解密key/私钥路径]")
        sys.exit(1)
    enc_path = sys.argv[1]
    output_dir = sys.argv[2]
    key_or_priv = sys.argv[3] if len(sys.argv) > 3 else None
    # 检查flag
    with open(enc_path, "rb") as f:
        file_flag = f.read(16)
    if file_flag != ENCRYPT_FLAG:
        print("[!] 不是本工具加密的模型文件，终止解密。")
        sys.exit(1)
    # 读取剩余内容
    with open(enc_path, "rb") as f:
        f.seek(16)
        enc_data = f.read()
    # 临时写入去除flag的文件，后续流程复用
    tmp_enc_path = enc_path + ".tmp"
    with open(tmp_enc_path, "wb") as f:
        f.write(enc_data)
    meta, meta_len = extract_meta_from_file(tmp_enc_path)
    mode = meta.get("mode", "xor")
    model_name = os.path.basename(enc_path).replace(".enc", "")
    out_file = os.path.join(output_dir, model_name)
    print(f"检测到加密模式: {mode}")
    if mode == "xor":
        decrypt_key = key_or_priv or meta["decrypt_key"]
        key_bytes = bytes.fromhex(decrypt_key)
        with open(tmp_enc_path, "rb") as f:
            enc_data = f.read()
        idx = enc_data.rfind(b"__META__")
        if idx == -1:
            raise ValueError("未找到元数据标记 __META__，无法解密")
        enc_content = enc_data[:idx]
        decrypted = xor_decrypt(enc_content, key_bytes)
        with open(out_file, "wb") as f:
            f.write(decrypted)
        # 校验md5
        import hashlib
        md5_actual = hashlib.md5(decrypted).hexdigest()
        md5_expected = meta["model_md5"]
        if md5_actual == md5_expected:
            print(f"✅ 解密后模型md5校验通过: {md5_actual}")
        else:
            print(f"❌ 解密后模型md5校验失败: {md5_actual} ≠ {md5_expected}")
        print(f"解密完成，输出文件: {out_file}")
    elif mode == "hybrid":
        priv_path = key_or_priv or RSA_PRIVATE_KEY_PATH
        private_key = load_rsa_private_key(priv_path)
        encrypted_aes_key = b64decode(meta["aes_key_rsa"])
        aes_key = private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        aes_decrypt_file(tmp_enc_path, out_file, aes_key, meta["iv"], meta_len)
        # 校验md5
        import hashlib
        with open(out_file, "rb") as f:
            decrypted = f.read()
        md5_actual = hashlib.md5(decrypted).hexdigest()
        md5_expected = meta["model_md5"]
        if md5_actual == md5_expected:
            print(f"✅ 解密后模型md5校验通过: {md5_actual}")
        else:
            print(f"❌ 解密后模型md5校验失败: {md5_actual} ≠ {md5_expected}")
        print(f"解密完成，输出文件: {out_file}")
    else:
        raise ValueError(f"不支持的加密模式: {mode}")
    # 清理临时文件
    os.remove(tmp_enc_path)

if __name__ == "__main__":
    main()

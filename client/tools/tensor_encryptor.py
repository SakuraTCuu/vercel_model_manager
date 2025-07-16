# -*- coding: utf-8 -*-
import os
import sys
import argparse
import secrets

# ========== 配置 ========== #
# 写死的默认key（16字节hex字符串，32位）
DEFAULT_KEY = "3f40bba6a0444dcd887f6e7c5afa3dee"

# ========== 工具函数 ========== #
def random_key(length=16):
    return secrets.token_hex(length)

def xor_encrypt(data, key_bytes):
    return bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data)])

# ========== safetensors 加密 ========== #
def encrypt_safetensors(model_path, output_path, key_hex):
    key_bytes = bytes.fromhex(key_hex)
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
    return out_file

# ========== ckpt/pt 加密 ========== #
def encrypt_ckpt_pt(model_path, output_path, key_hex):
    import torch
    key_bytes = bytes.fromhex(key_hex)
    state = torch.load(model_path, map_location="cpu")
    if "state_dict" in state:
        weights = state["state_dict"]
    else:
        weights = state
    encrypted_weights = {}
    for k, v in weights.items():
        if hasattr(v, 'numpy'):
            arr = v.cpu().numpy().view('uint8')
            flat = arr.flatten()
            enc = (flat ^ key_bytes[0])  # 简单xor
            enc = enc.reshape(arr.shape)
            encrypted_weights[k] = torch.from_numpy(enc).to(v.dtype)
        else:
            encrypted_weights[k] = v  # 跳过非tensor
    if "state_dict" in state:
        state["state_dict"] = encrypted_weights
        out_file = os.path.join(output_path, os.path.basename(model_path))
        torch.save(state, out_file)
    else:
        out_file = os.path.join(output_path, os.path.basename(model_path))
        torch.save(encrypted_weights, out_file)
    return out_file

# ========== 主流程 ========== #
def encrypt_model(model_path, output_path, key_hex):
    ext = os.path.splitext(model_path)[1].lower()
    if ext == ".safetensors":
        return encrypt_safetensors(model_path, output_path, key_hex)
    elif ext in [".ckpt", ".pt"]:
        return encrypt_ckpt_pt(model_path, output_path, key_hex)
    else:
        print(f"不支持的模型格式: {ext}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="模型权重加密工具，支持ckpt/pt/safetensors。默认key可在脚本内修改，传--key参数可覆盖。")
    parser.add_argument("model_path", help="原始模型路径")
    parser.add_argument("output_path", help="加密模型输出目录")
    parser.add_argument("--key", type=str, help="自定义32位hex key（16字节）")
    args = parser.parse_args()

    # 优先用参数key，否则用写死key
    if args.key:
        if len(args.key) != 32:
            print("自定义key必须是32位hex字符串（16字节）")
            sys.exit(1)
        key_hex = args.key
    else:
        key_hex = DEFAULT_KEY

    out_file = encrypt_model(args.model_path, args.output_path, key_hex)
    print(f"加密完成！输出文件: {out_file}\n加密key: {key_hex}")

if __name__ == "__main__":
    main()

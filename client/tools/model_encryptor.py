import os
import uuid
import json
import struct
import argparse
from typing import Tuple, Dict, Any

VERSION = 1
META_KEY = "wk_enc"
ALG_NAME = "rev-tensor"  # 单一算法：逐 tensor 数据段翻转


# ------------------------------------------------------------------
# 低层 I/O
# ------------------------------------------------------------------
def read_safetensors_file(path: str) -> Tuple[int, bytes, bytes, Dict[str, Any]]:
    """返回 (header_len, header_bytes, data_bytes, header_obj)。"""
    with open(path, "rb") as f:
        hl_bytes = f.read(8)
        if len(hl_bytes) != 8:
            raise RuntimeError(f"{path}: 文件太短，无法读取 header_len。")
        header_len = struct.unpack("<Q", hl_bytes)[0]

        header_bytes = f.read(header_len)
        if len(header_bytes) != header_len:
            raise RuntimeError(f"{path}: header 长度不符，期望 {header_len} 实际 {len(header_bytes)}。")

        data_bytes = f.read()

    try:
        header_obj = json.loads(header_bytes.decode("utf-8"))
        print("header_obj", header_obj)
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"{path}: header JSON 解析失败: {e}") from e

    return header_len, header_bytes, data_bytes, header_obj


def write_safetensors_file(path: str, header_bytes: bytes, data_bytes: bytes):
    """写 safetensors 文件。"""
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(header_bytes)))
        f.write(header_bytes)
        f.write(data_bytes)


# ------------------------------------------------------------------
# 逐 tensor 数据翻转
# ------------------------------------------------------------------
def reverse_tensors_in_data(data: bytes, header_obj: Dict[str, Any]) -> bytes:
    """
    对 header 中每个 tensor 的 [start:end) 区间单独翻转。
    不改 offset，不改长度——布局无变化，合法。
    """
    out = bytearray(data)
    total = len(out)
    for name, info in header_obj.items():
        if name.startswith("__"):  # 跳过 __metadata__
            continue
        try:
            start, end = info["data_offsets"]
        except Exception:
            continue
        if not (0 <= start <= end <= total):
            print(f"[wk-enc] WARN: tensor {name} offsets越界({start},{end}/{total})，跳过。")
            continue
        out[start:end] = out[start:end][::-1]
    return bytes(out)


# ------------------------------------------------------------------
# 检测已加密
# ------------------------------------------------------------------
def detect_wk_enc(header_obj: Dict[str, Any]):
    """
    如果 header 已含 wk_enc 元数据，返回其值；否则返回 None。
    值可能是 str (新格式) 或 dict (旧格式)。
    """
    meta = header_obj.get("__metadata__", {})
    if not isinstance(meta, dict):
        return None
    wk_meta = meta.get(META_KEY)
    return wk_meta


# ------------------------------------------------------------------
# 主加密流程
# ------------------------------------------------------------------
def encrypt_model(input_path: str, output_path: str, model_id: str | None, force: bool):
    """
    加密模型文件
    
    Args:
        input_path: 输入的原始模型文件路径
        output_path: 输出的加密模型文件路径  
        model_id: 32位模型ID（实际就是后端的api_key），将写入metadata用于验证
        force: 是否强制覆盖已加密的文件
    """
    # 读取
    _, orig_header_bytes, orig_data_bytes, header_obj = read_safetensors_file(input_path)

    # 已加密检查
    existed = detect_wk_enc(header_obj)
    if existed is not None:
        if not force:
            raise RuntimeError(
                f"{input_path} 已包含 wk_enc 元数据；如果要重新加密请添加 --force。"
            )
        print("[wk-enc] WARNING: 输入文件已带 wk_enc，按 --force 覆盖。")

    # model_id
    if not model_id or len(model_id) != 32:
        print(f"[wk-enc] model_id 非32位，自动生成: {model_id}")
        model_id = uuid.uuid4().hex
    
    print(f"[wk-enc] 使用 model_id (api_key): {model_id}")

    # metadata root
    meta = header_obj.get("__metadata__", {})
    if not isinstance(meta, dict):
        meta = {}

    # wk_enc payload MUST be a *string* (safetensors metadata 要求 value=string)
    wk_payload_str = json.dumps(
        {
            "ver": VERSION,
            "model_id": model_id,  # model_id就是api_key，客户端将用此值向后端验证
            "alg": ALG_NAME,
            "enc": True,
            "datalen": len(orig_data_bytes),
        },
        separators=(",", ":"),
    )
    meta[META_KEY] = wk_payload_str
    header_obj["__metadata__"] = meta

    # 重新编码 header
    new_header_bytes = json.dumps(
        header_obj, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")

    # 加密：逐 tensor 翻转
    enc_data = reverse_tensors_in_data(orig_data_bytes, header_obj)

    # 输出
    write_safetensors_file(output_path, new_header_bytes, enc_data)

    print(f"[OK] Encrypted safetensors (alg={ALG_NAME}) -> {output_path}")
    print(f"[INFO] Model ID (api_key): {model_id}")
    print(f"[INFO] Header size={len(new_header_bytes)} Data size={len(enc_data)}")


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Encrypt safetensors (wk_enc rev-tensor).")
    ap.add_argument("-i", "--input", required=True, help="Input .safetensors file")
    ap.add_argument("-o", "--output", required=True, help="Output encrypted .safetensors file")
    ap.add_argument("-m", "--model_id", default=None, help="32-char model ID (实际就是api_key); auto-generated if omitted")
    ap.add_argument("--force", action="store_true", help="Overwrite if file already marked wk_enc")
    args = ap.parse_args()

    encrypt_model(args.input, args.output, args.model_id, args.force)


if __name__ == "__main__":
    main()

import struct

MAGIC = b"iswk_enc"
HEADER_SIZE = 54

def xor_data(data: bytes, key: bytes) -> bytes:
    key_len = len(key)
    return bytes([b ^ key[i % key_len] for i, b in enumerate(data)])

def decrypt_model(enc_path, out_path, key_str):
    key = key_str.encode("utf-8")
    with open(enc_path, "rb") as f:
        header = f.read(HEADER_SIZE)
        magic = header[:8]
        if magic != MAGIC:
            raise ValueError("Not a valid encrypted model file!")
        file_size = struct.unpack("<Q", header[10:18])[0]
        enc_data = f.read()

    dec_data = xor_data(enc_data, key)
    with open(out_path, "wb") as f:
        f.write(dec_data)
    print(f"[OK] Decrypted model saved to {out_path}")

if __name__ == "__main__":
    decrypt_model(r".\sec_model\wk.enc", r".\sec_model\dec_test.safetensors", "2059f504af7a437494397f45b61e00d6")

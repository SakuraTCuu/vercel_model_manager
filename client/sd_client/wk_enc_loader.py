"""
wk_enc_loader.py -- wk encrypted safetensors loader for A1111 SD-WebUI

Supported algorithms (metadata __metadata__.wk_enc.alg):
  * "rev-tensor"   - each tensor data range reversed (current main scheme)
  * "reverse-only" - whole data block reversed (legacy test)
  * "xor-ascii"    - whole data block XOR with ascii key (legacy test)

Usage:
  Drop this file under extensions/wk_enc_loader/scripts/.
  Restart webui. Select encrypted .safetensors in model list; loader decrypts transparently.
"""

import io
import os
import json
import struct
import torch  # imported because webui usually imports torch before sd_models
import modules.sd_models as sd_models

# safetensors import ----------------------------------------------------------
try:
    import safetensors.torch as st
    HAVE_SAFETENSORS = True
except Exception as e:  # pragma: no cover
    print(f"[wk-enc] safetensors not available: {e}")
    HAVE_SAFETENSORS = False

META_KEY = "wk_enc"

# -----------------------------------------------------------------------------
# Original loader save
# -----------------------------------------------------------------------------
ORIGINAL_READ_STATE_DICT = getattr(sd_models, "read_state_dict", None)
if ORIGINAL_READ_STATE_DICT is None:
    raise RuntimeError("[wk-enc] ERROR: sd_models.read_state_dict not found; plugin cannot install.")

print("[wk-enc] Extension loaded. Hooking sd_models.read_state_dict ...")


# -----------------------------------------------------------------------------
# Helpers
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
        print(f"[wk-enc] Using env WK_XOR_KEY: {k}")
        return k
    mid = meta.get("model_id")
    if mid:
        print(f"[wk-enc] Using model_id as key: {mid}")
        return mid
    k = "wk_default_key_change_me"
    print(f"[wk-enc] Using built-in fallback key: {k}")
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
        print(f"[wk-enc] _parse_header fail for {path}: {e}")
        return None


# -----------------------------------------------------------------------------
# Algorithm implementations
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
            print(f"[wk-enc] WARN offset out of range for tensor {name}: {start}-{end}/{len(out)}")
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


# -----------------------------------------------------------------------------
# Core decrypt of file -> full safetensors bytes
# -----------------------------------------------------------------------------
def _decrypt_safetensors_file(path: str, alg: str, meta: dict,
                              header_len: int, header_bytes: bytes, header_obj: dict) -> bytes:
    """
    Read encrypted file's data block, decrypt by alg, return full safetensors bytes (header+data).
    """
    with open(path, "rb") as f:
        f.seek(8 + header_len)
        data_enc = f.read()

    if alg == "rev-tensor":
        print(f"[wk-enc] decrypt alg=rev-tensor (per tensor)...")
        data_dec = _decrypt_rev_tensor(data_enc, header_obj)
    elif alg == "reverse-only":
        print(f"[wk-enc] decrypt alg=reverse-only (whole block)...")
        data_dec = _decrypt_reverse_only(data_enc)
    elif alg == "xor-ascii":
        print(f"[wk-enc] decrypt alg=xor-ascii (whole block)...")
        data_dec = _decrypt_xor_ascii(data_enc, meta)
    else:
        raise RuntimeError(f"[wk-enc] Unknown wk_enc alg: {alg}")

    full_bytes = struct.pack("<Q", len(header_bytes)) + header_bytes + data_dec
    return full_bytes


# -----------------------------------------------------------------------------
# Load safetensors from in-memory bytes (newer safetensors supports bytes)
# Includes fallback to BytesIO for safety.
# -----------------------------------------------------------------------------
def _load_safetensors_from_bytes(data: bytes):
    try:
        return st.load(data)
    except Exception as e:
        print(f"[wk-enc] st.load(bytes) failed: {e}")
        raise



# -----------------------------------------------------------------------------
# Hook: read_state_dict
# -----------------------------------------------------------------------------
def wk_read_state_dict(checkpoint_file, print_global_state=False, map_location=None):
    print(f"[wk-enc] >>> wk_read_state_dict: {checkpoint_file}")
    low = checkpoint_file.lower()

    if HAVE_SAFETENSORS and low.endswith(".safetensors"):
        parsed = _parse_header(checkpoint_file)
        if parsed is not None:
            header_len, header_bytes, header_obj = parsed
            meta_root = header_obj.get("__metadata__", {})
            wk_meta = meta_root.get(META_KEY)
            if isinstance(wk_meta, str):
                try:
                    wk_meta = json.loads(wk_meta)
                except Exception as e:
                    print(f"[wk-enc] wk_meta json decode failed: {e}")
                    wk_meta = None

            if wk_meta and wk_meta.get("enc"):
                alg = wk_meta.get("alg", "?")
                print(f"[wk-enc] encrypted safetensors detected: alg={alg}")
                try:
                    full_bytes = _decrypt_safetensors_file(
                        checkpoint_file, alg, wk_meta,
                        header_len, header_bytes, header_obj
                    )
                    sd = _load_safetensors_from_bytes(full_bytes)
                    print("[wk-enc] returning decrypted state_dict.")
                    return sd
                except Exception as e:
                    print(f"[wk-enc] ERROR decrypt/load: {e}")
                    # raise here so A1111 doesn't try to parse encrypted bytes
                    raise

    # fallback normal loader
    return ORIGINAL_READ_STATE_DICT(
        checkpoint_file,
        print_global_state=print_global_state,
        map_location=map_location
    )


# -----------------------------------------------------------------------------
# Install hook
# -----------------------------------------------------------------------------
sd_models.read_state_dict = wk_read_state_dict
print("[wk-enc] sd_models.read_state_dict successfully hooked (wk_enc_loader rev-tensor).")

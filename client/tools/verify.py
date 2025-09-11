import hashlib

def file_md5(path):
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)
    return md5.hexdigest()

print("Original:", file_md5(r".\src_model\test.safetensors"))
print("Decrypted:", file_md5(r".\sec_model\wk.safetensors"))
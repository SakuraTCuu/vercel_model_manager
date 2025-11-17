import os
import sys
import importlib.util
import tempfile

# ComfyUI 的模块导入
try:
    import comfy.sd
    import folder_paths
    COMFY_AVAILABLE = True
    print("[Final Model Loader] ✅ ComfyUI 模块导入成功")
except ImportError as e:
    COMFY_AVAILABLE = False
    print(f"[Final Model Loader] ❌ ComfyUI 模块导入失败: {e}")
    raise

# 尝试导入 safetensors
try:
    import safetensors.torch as st
    HAVE_SAFETENSORS = True
except ImportError:
    HAVE_SAFETENSORS = False
    print("⚠️ safetensors 未安装，加密模型功能可能受限")

print("=== 🔐 Final Model Loader 启动初始化 ===")

# 动态加载你的核心解密模块
current_dir = os.path.dirname(os.path.abspath(__file__))
final_loader_path = os.path.join(current_dir, "final_model_loader.py")

try:
    # 动态导入你的解密模块
    spec = importlib.util.spec_from_file_location("final_model_loader", final_loader_path)
    final_loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(final_loader)
    
    print("✅ 成功加载 Final Model Loader 核心模块")
    
except Exception as e:
    print(f"❌ 加载核心模块失败: {e}")
    raise

# 保存原始加载函数
_original_load_checkpoint = None
if hasattr(comfy.sd, 'load_checkpoint_guess_config'):
    _original_load_checkpoint = comfy.sd.load_checkpoint_guess_config
    print("✅ 找到 comfy.sd.load_checkpoint_guess_config 函数")
else:
    print("❌ 无法找到 load_checkpoint_guess_config 函数")
    print(f"[DEBUG] comfy.sd 可用属性: {dir(comfy.sd)}")

# 缓存已处理的模型，避免重复检测和解密
_model_cache = {}
_decrypted_cache = {}  # 缓存解密结果

def _patched_load_checkpoint(checkpoint_path, **kwargs):
    """
    被补丁的模型加载函数 - 自动拦截所有模型加载请求
    """
    # 检查缓存，避免重复打印
    cache_key = f"{checkpoint_path}_{str(sorted(kwargs.items()))}"
    
    # 首次加载时打印
    if cache_key not in _model_cache:
        print(f"[final-loader] 尝试加载模型: {checkpoint_path}")
    
    # 使用你现有的检测逻辑判断是否为加密模型
    is_encrypted, parsed_data = final_loader.detect_encrypted_model(checkpoint_path)
    
    if is_encrypted:
        # 首次加密模型检测时打印
        if cache_key not in _model_cache:
            print(f"🔐 检测到加密模型，开始解密: {checkpoint_path}")
        
        # 检查是否已经解密过
        if checkpoint_path in _decrypted_cache:
            if cache_key not in _model_cache:
                print(f"[final-loader] 使用缓存的解密结果")
                _model_cache[cache_key] = True
            return _decrypted_cache[checkpoint_path]
        
        try:
            # 使用你现有的解密逻辑
            state_dict = final_loader.final_read_state_dict(checkpoint_path)
            
            # 转换为 ComfyUI 格式 (需要适配)
            result = convert_state_dict_to_comfy(state_dict, checkpoint_path)
            
            # 缓存解密结果（注意：这会占用内存，对于大模型可能需要考虑）
            _decrypted_cache[checkpoint_path] = result
            
            # 缓存标记
            _model_cache[cache_key] = True
            
            print("✅ 模型解密加载成功")
            
            return result
            
        except Exception as e:
            print(f"❌ 解密失败: {e}")
            # 可以选择回退到原始加载器或直接抛出异常
            raise RuntimeError(f"加密模型加载失败: {e}")
    
    else:
        # 普通模型，走原始流程
        if cache_key not in _model_cache:
            print(f"[final-loader] 加载标准模型: {checkpoint_path}")
            _model_cache[cache_key] = True
        
        if _original_load_checkpoint:
            # ComfyUI 的 load_checkpoint_guess_config 不接受 output_dir 参数
            # 移除 output_dir，只传递 kwargs 中的其他参数
            return _original_load_checkpoint(checkpoint_path, **kwargs)
        else:
            raise RuntimeError("原始模型加载器不可用")

def convert_state_dict_to_comfy(state_dict, checkpoint_path):
    """
    关键函数：将解密后的 state_dict 转换为 ComfyUI 需要的 (model, clip, vae) 三元组
    
    策略：将解密后的 state_dict 保存到临时文件，然后让原始加载器读取
    这样可以复用 ComfyUI 的全部模型解析逻辑
    """
    if not HAVE_SAFETENSORS:
        raise RuntimeError("safetensors 未安装，无法转换加密模型")
    
    try:
        print("[final-loader] 开始转换 state_dict 为 ComfyUI 格式...")
        
        # 方案1: 创建临时文件，让原始加载器读取
        # 这是最安全的方式，因为它完全复用了 ComfyUI 的解析逻辑
        with tempfile.NamedTemporaryFile(suffix='.safetensors', delete=False) as tmp_file:
            tmp_path = tmp_file.name
            print(f"[final-loader] 创建临时文件: {tmp_path}")
            
            # 将解密后的 state_dict 保存为 safetensors 格式
            st.save_file(state_dict, tmp_path)
            print(f"[final-loader] state_dict 已保存到临时文件")
        
        try:
            # 使用原始加载器加载临时文件
            print(f"[final-loader] 调用原始加载器处理临时文件...")
            # 直接调用真正的原始函数，而不是经过 patch 的版本
            # 这样避免递归调用和参数问题
            result = _original_load_checkpoint(tmp_path)
            print(f"[final-loader] ✅ 成功转换为 ComfyUI 格式")
            return result
            
        finally:
            # 清理临时文件
            try:
                os.unlink(tmp_path)
                print(f"[final-loader] 已清理临时文件")
            except Exception as e:
                print(f"[final-loader] 清理临时文件失败: {e}")
        
    except Exception as e:
        print(f"❌ 模型格式转换失败: {e}")
        import traceback
        traceback.print_exc()
        raise

# 安装补丁
if _original_load_checkpoint:
    comfy.sd.load_checkpoint_guess_config = _patched_load_checkpoint
    print("✅ 成功安装模型加载补丁")
else:
    print("❌ 补丁安装失败：原始加载器不可用")

# 注册加密模型文件扩展名（可选）
folder_paths.supported_pt_extensions |= {'.encrypted', '.safeenc'}
print("✅ 已注册加密模型文件扩展名")

print("=== 🔐 Final Model Loader 初始化完成 ===")
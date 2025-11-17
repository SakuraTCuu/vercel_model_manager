# 🔐 Final Model Loader for ComfyUI - 加密模型加载器
# 这是一个启动时自动加载的 hook 插件，不提供 UI 节点

print("🔐 Final Model Loader for ComfyUI - 加密模型加载器 - 开始加载")

# 导入并执行启动脚本
import os
import sys
import importlib.util

# 获取当前目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 使用 importlib 动态导入并执行 prestartup_script.py
prestartup_path = os.path.join(current_dir, "prestartup_script.py")

if os.path.exists(prestartup_path):
    print(f"[Final Model Loader] 正在执行启动脚本: {prestartup_path}")
    try:
        # 使用 importlib 动态导入（这样可以正确处理 import 语句）
        spec = importlib.util.spec_from_file_location("prestartup_script", prestartup_path)
        prestartup_module = importlib.util.module_from_spec(spec)
        sys.modules['prestartup_script'] = prestartup_module
        spec.loader.exec_module(prestartup_module)
        
        print("[Final Model Loader] ✅ 启动脚本执行成功")
    except Exception as e:
        print(f"[Final Model Loader] ❌ 启动脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"[Final Model Loader] ⚠️ 找不到启动脚本: {prestartup_path}")

# ComfyUI 要求自定义节点必须导出 NODE_CLASS_MAPPINGS
# 由于这是一个后台 hook 插件，我们提供空映射
NODE_CLASS_MAPPINGS = {}

# 可选：提供插件的显示名称
__all__ = ['NODE_CLASS_MAPPINGS']
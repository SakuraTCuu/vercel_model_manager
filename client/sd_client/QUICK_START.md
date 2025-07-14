# SecureModelLoader 快速开始指南

## 🚀 5分钟快速配置

### 步骤1: 下载文件
将以下文件复制到 Stable Diffusion WebUI 的 `extensions` 目录：
- `secure_loader.py`
- `config.py`

### 步骤2: 获取API密钥
1. 访问管理界面：https://vercel-model-manager.vercel.app/
2. 登录管理员账户
3. 创建新的API密钥
4. 复制生成的密钥

### 步骤3: 配置脚本
编辑 `config.py`，填入你的API密钥：
```python
API_KEY = "your-actual-api-key-here"  # 替换为你的实际密钥
```

### 步骤4: 测试连接
运行测试脚本验证配置：
```bash
python test_verify_key.py
```

### 步骤5: 重启WebUI
重启 Stable Diffusion WebUI，脚本会自动加载。

## ✅ 验证安装

1. 在WebUI中，你应该能看到 "Secure Model Loader" 选项
2. 查看日志文件 `secure_loader.log` 确认初始化成功
3. 尝试加载一个加密模型文件

## 🔧 常见问题快速解决

### 问题1: API密钥未设置
**错误**: `API密钥未设置，请在config.py中配置API_KEY`
**解决**: 在 `config.py` 中设置 `API_KEY = "你的密钥"`

### 问题2: 网络连接失败
**错误**: `无法连接到许可证服务器`
**解决**: 
- 检查网络连接
- 确认可以访问 https://vercel-model-manager.vercel.app/
- 检查防火墙设置

### 问题3: 服务器拒绝请求
**错误**: `授权失败: 无效或已停用的key`
**解决**:
- 检查API密钥是否正确
- 确认密钥在后端管理界面中状态为启用
- 检查设备是否在白名单中

### 问题4: 模型不被识别
**错误**: `文件扩展名不匹配`
**解决**: 在 `config.py` 中添加支持的扩展名：
```python
MODEL_EXTENSIONS = [".safetensors", ".ckpt", ".pt", ".bin"]
```

## 📞 获取帮助

如果遇到问题：
1. 查看 `secure_loader.log` 日志文件
2. 运行 `test_verify_key.py` 测试脚本
3. 检查配置文件设置
4. 联系技术支持

## 🎯 下一步

配置完成后，你可以：
- 加载加密的模型文件
- 查看详细的运行日志
- 自定义支持的模型格式
- 实现实际的解密算法 
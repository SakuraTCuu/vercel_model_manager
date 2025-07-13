# SecureModelLoader 使用说明

## 概述

SecureModelLoader 是一个用于 Stable Diffusion 的安全模型加载器，支持加密模型的验证和解密。它通过后端API进行密钥验证，确保只有授权用户才能加载加密模型。

## 文件结构

```
client/
├── secure_loader.py    # 主脚本文件
├── config.py          # 配置文件
├── README.md          # 使用说明
└── test_verify_key.py # 测试脚本
```

## 安装和配置

### 1. 文件放置

将以下文件复制到 Stable Diffusion WebUI 的 `extensions` 目录下的任意子目录中：
- `secure_loader.py`
- `config.py`

### 2. 配置设置

编辑 `config.py` 文件，设置以下参数：

```python
# API服务器配置（已配置为Vercel部署地址）
SERVER_URL = "https://vercel-model-manager.vercel.app/api/verify-key"

# API密钥配置（从后端管理界面获取）
API_KEY = "your-api-key-here"  # 请填入您的API密钥

# 网络配置
TIMEOUT = 15  # 请求超时时间（秒）

# 日志配置
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = "secure_loader.log"

# 模型配置
MODEL_EXTENSIONS = [".safetensors", ".ckpt", ".pt"]  # 支持的模型文件扩展名
```

### 3. 获取API密钥

1. 访问后端管理界面：https://vercel-model-manager.vercel.app/
2. 在API密钥管理页面创建新的API密钥
3. 将生成的密钥填入 `config.py` 中的 `API_KEY` 字段

### 4. 测试连接

在配置完成后，可以运行测试脚本验证连接：

```bash
python test_verify_key.py
```

测试脚本会：
- 检查服务器健康状态
- 验证API连接
- 测试设备信息获取
- 验证响应格式

## 工作原理

### 1. 模型识别

脚本会检查模型文件的metadata信息，寻找 `encrypted_by: "SecureModelLoader"` 标识来判断是否为加密模型。

### 2. 设备验证

当检测到加密模型时，脚本会：
- 获取设备的MAC地址和CPU信息
- 向后端API发送验证请求
- 后端验证API密钥的有效性和设备绑定情况

### 3. 密钥获取

验证成功后，后端会返回：
- `xorResult`: 经过异或加密的解密密钥
- `timestamp`: 时间戳

### 4. 密钥解码

脚本使用时间戳对 `xorResult` 进行异或解码，得到实际的解密密钥。

### 5. 模型解密

使用解码后的密钥对模型数据进行解密（目前为占位实现）。

## 日志文件

脚本会在同目录下生成 `secure_loader.log` 日志文件，记录详细的运行信息，包括：
- 模型验证过程
- 网络请求详情
- 错误信息
- 解密过程

## 故障排除

### 常见问题

1. **API密钥未设置**
   - 错误信息：`API密钥未设置，请在config.py中配置API_KEY`
   - 解决方案：在 `config.py` 中设置正确的API密钥

2. **网络连接失败**
   - 错误信息：`无法连接到许可证服务器`
   - 解决方案：检查网络连接，确保可以访问 https://vercel-model-manager.vercel.app/

3. **服务器拒绝请求**
   - 错误信息：`授权失败: [具体错误信息]`
   - 解决方案：检查API密钥是否有效，设备是否在白名单中

4. **模型格式不支持**
   - 错误信息：`文件扩展名不匹配`
   - 解决方案：在 `config.py` 中添加支持的扩展名

5. **Vercel部署相关问题**
   - 如果遇到CORS错误，请检查请求头设置
   - 如果遇到超时，可能需要调整 `TIMEOUT` 值
   - 确保使用HTTPS协议访问

### 调试模式

将 `config.py` 中的 `LOG_LEVEL` 设置为 `"DEBUG"` 可以获得更详细的日志信息：

```python
LOG_LEVEL = "DEBUG"
```

### 测试脚本使用

1. 编辑 `test_verify_key.py`，设置 `TEST_API_KEY` 变量
2. 运行测试脚本：
   ```bash
   python test_verify_key.py
   ```
3. 根据测试结果调整配置

## 安全注意事项

1. **API密钥安全**
   - 不要将API密钥提交到版本控制系统
   - 定期更换API密钥
   - 限制API密钥的访问权限

2. **网络安全**
   - 使用HTTPS协议（已配置）
   - 配置防火墙规则
   - 监控异常访问

3. **设备绑定**
   - 后端会自动绑定首次使用的设备MAC地址
   - 如需更换设备，请联系管理员添加到白名单

4. **Vercel部署安全**
   - 确保环境变量正确设置
   - 定期检查部署日志
   - 监控API使用情况

## 开发说明

### 扩展支持的文件格式

在 `config.py` 中的 `MODEL_EXTENSIONS` 列表中添加新的扩展名：

```python
MODEL_EXTENSIONS = [".safetensors", ".ckpt", ".pt", ".bin"]
```

### 实现实际解密逻辑

在 `secure_loader.py` 的 `decrypt_model` 方法中实现实际的解密算法：

```python
def decrypt_model(self, encrypted_data: Any, key: str) -> Dict[str, Any]:
    # TODO: 实现实际的解密逻辑
    # 使用 key 对 encrypted_data 进行解密
    # 返回解密后的模型数据
    pass
```

### Vercel部署注意事项

1. **环境变量**
   - 确保在Vercel中正确设置了数据库连接字符串
   - 检查其他必要的环境变量

2. **API限制**
   - Vercel有请求大小和超时限制
   - 注意冷启动时间

3. **监控**
   - 使用Vercel Analytics监控API使用情况
   - 设置错误告警

## 联系支持

如遇到问题，请：
1. 查看日志文件 `secure_loader.log`
2. 运行测试脚本 `test_verify_key.py`
3. 检查配置文件设置
4. 联系技术支持并提供详细的错误信息

## 更新日志

- **v1.0.0**: 初始版本，支持基本的模型验证和解密
- **v1.1.0**: 适配Vercel部署，添加配置文件支持
- **v1.1.1**: 添加测试脚本，改进错误处理 
# 企业微信错误通知配置

## 功能说明

当应用发生任何未捕获的异常时，会自动通过企业微信 webhook 推送错误信息到指定群聊。

## 配置步骤

### 1. 设置环境变量

在 Render 或本地环境中添加：

```bash
WECHAT_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=e4296aab-14eb-4ad2-a4df-15abec50760d
```

### 2. 在 Render Dashboard 配置

1. 登录 Render Dashboard
2. 选择你的 Web Service
3. 进入「Environment」标签
4. 添加新变量：
   - **Key**: `WECHAT_WEBHOOK_URL`
   - **Value**: `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key`
5. 点击「Save Changes」并等待重新部署

### 3. 测试配置

运行测试脚本：

```bash
python test_wechat_notification.py
```

## 推送内容

错误通知包含以下信息：

- 🚨 **错误类型**：异常类名
- ⏰ **时间戳**：错误发生时间
- 🔗 **请求路径**：触发错误的 API 端点
- 👤 **用户ID**：发生错误的用户（如果已登录）
- 📝 **错误信息**：完整错误描述
- 📋 **上下文**：请求参数、方法等
- 🐛 **堆栈信息**：最后10行 traceback

## 示例推送格式

```markdown
## 🚨 Connact.ai 错误报警

**时间**: 2026-02-04 15:30:00
**错误类型**: `ValueError`
**请求路径**: `/api/generate-email`
**用户ID**: `usr_abc123xyz`

**错误信息**:
```
Invalid email format
```

**上下文**:
```json
{
  "method": "POST",
  "form_keys": ["sender_profile", "receiver_name"]
}
```

**堆栈信息** (最后10行):
```python
  File "app.py", line 500, in generate_email_api
    email = generate_email(sender, receiver)
  File "src/email_agent.py", line 200, in generate_email
    raise ValueError("Invalid email format")
ValueError: Invalid email format
```
```

## 手动推送通知

在代码中手动触发通知：

```python
from src.services.error_notifier import notify_error

try:
    risky_operation()
except Exception as e:
    notify_error(
        e,
        context={"operation": "generate_email", "retry_count": 3},
        user_id=session.get("user_id"),
        request_path=request.path
    )
    # 可以选择重新抛出异常或处理
    raise
```

## 发送普通消息

```python
from src.services.error_notifier import error_notifier

# 发送纯文本消息
error_notifier.notify_info("部署完成！新版本已上线 🚀")
```

## 禁用通知

如果需要临时禁用错误通知，移除或清空环境变量：

```bash
unset WECHAT_WEBHOOK_URL
```

## 故障排查

### 通知未收到？

1. 检查环境变量是否正确设置
2. 检查 webhook URL 是否有效（在浏览器访问会提示错误，这是正常的）
3. 查看应用日志是否有 "Failed to send error notification" 错误
4. 确认企业微信机器人未被限流（最高频率: 20条/分钟）

### 测试 webhook

使用 curl 测试：

```bash
curl -X POST https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key \
  -H 'Content-Type: application/json' \
  -d '{
    "msgtype": "text",
    "text": {
      "content": "测试消息"
    }
  }'
```

返回 `{"errcode":0,"errmsg":"ok"}` 表示成功。

## 安全建议

1. **不要将 webhook URL 提交到代码库**
2. **定期更换 webhook key**（在企业微信群设置中重新生成）
3. **限制 webhook 的使用范围**（只在生产环境启用）

## 错误捕获机制（2026-02-06 增强）

### 三层防护体系

系统采用三层错误捕获机制，确保所有错误都能被监控：

1. **全局异常处理器** (`@app.errorhandler(Exception)`):
   - 捕获所有未处理异常
   - 自动提取请求上下文（method, path, args, API data）
   - 过滤敏感信息（密码、token 等）
   - 适用于所有 HTTP 请求

2. **关键 API 端点显式通知**:
   - `/api/upload-sender-pdf` - 文件上传错误
   - `/api/generate-email` - 邮件生成错误
   - `/api/find-recommendations` - 推荐查找错误
   - `/api/apollo/unlock-email` - Apollo API 错误
   - 更多端点持续完善中...

3. **HTTP 错误处理器**:
   - `@app.errorhandler(404)` - Not Found
   - `@app.errorhandler(500)` - Internal Server Error

### 上下文信息增强

最新的错误通知包含更丰富的上下文：

```python
context = {
    "method": "POST",
    "path": "/api/find-recommendations",
    "args": {"deep_search": "true"},
    "form_keys": ["sender_profile"],
    "api_data": {  # 仅包含安全字段
        "purpose": "networking",
        "field": "ai research",
        "goal": "collaboration"
    }
}
```

**安全保护**: 自动过滤密码、token、API keys 等敏感信息。

### 测试命令

运行完整测试套件：

```bash
# 设置环境变量
export WECHAT_WEBHOOK_URL='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY'

# 运行测试（会发送 4 条测试消息）
python test_wechat_error_notification.py
```

测试包含：
- ✅ 基础错误通知
- ✅ API 错误场景模拟
- ✅ 复杂堆栈跟踪
- ✅ 信息通知

## 生产环境最佳实践

### 1. 分环境配置

为不同环境使用不同的 webhook URL：

- **开发环境**: 使用测试群（可关闭或使用低频告警）
- **生产环境**: 使用正式告警群（7x24 监控）

### 2. 响应流程

收到错误通知后：

```
1. 查看错误类型和频率（单次 vs 批量）
2. 检查用户 ID（是否影响多个用户）
3. 查看请求路径（定位功能模块）
4. 分析堆栈信息（技术诊断）
5. 查看业务上下文（复现场景）
6. 修复 + 部署 + 验证
```

### 3. 告警优化（可选）

如遇到大量重复错误，可添加去重逻辑：

```python
# 在 src/services/error_notifier.py 中
class ErrorNotifier:
    def __init__(self):
        self.recent_errors = {}  # {error_key: timestamp}
        self.dedup_window = 300  # 5分钟去重窗口
    
    def notify_error(self, error, ...):
        error_key = f"{type(error).__name__}:{str(error)[:50]}"
        now = time.time()
        
        if error_key in self.recent_errors:
            if now - self.recent_errors[error_key] < self.dedup_window:
                return True  # 跳过重复通知
        
        self.recent_errors[error_key] = now
        # ... 继续正常通知流程
```

## 开发文档

### 添加新的错误通知点

在需要监控的代码位置添加：

```python
from src.services.error_notifier import error_notifier
from app import ERROR_NOTIFICATION_ENABLED

@app.route('/api/your-endpoint', methods=['POST'])
def your_api_endpoint():
    try:
        # 你的业务逻辑
        result = do_something()
        return jsonify(result), 200
    except Exception as e:
        # 发送错误通知
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={
                    "operation": "your_operation",
                    "input_param": request.json.get("param")
                },
                user_id=session.get('user_id'),
                request_path='/api/your-endpoint'
            )
        # 返回错误响应
        return jsonify({'error': str(e)}), 500
```

### 核心文件

- `src/services/error_notifier.py` - 错误通知服务实现
- `app.py` - 全局错误处理器和 API 路由
- `test_wechat_error_notification.py` - 测试脚本
- `docs/wechat-error-notification.md` - 本文档

## 更新日志

- **2026-02-06**: 增强全局异常处理器，添加 API 数据上下文和敏感信息过滤
- **2026-02-06**: 为 `/api/upload-sender-pdf`, `/api/generate-email`, `/api/find-recommendations` 添加显式错误通知
- **2026-02-06**: 创建统一测试脚本 `test_wechat_error_notification.py`
- **Earlier**: 初始实现企业微信错误通知功能

## 参考文档

- [企业微信群机器人配置说明](https://developer.work.weixin.qq.com/document/path/91770)
- [项目开发日志](../devlog.md) - 查看最新更新

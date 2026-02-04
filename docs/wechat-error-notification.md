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

## 参考文档

- [企业微信群机器人配置说明](https://developer.work.weixin.qq.com/document/path/91770)

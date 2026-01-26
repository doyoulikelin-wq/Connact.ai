# 开发者模式 (Developer Mode)

开发者模式允许特定用户在每次 LLM 调用时选择使用的模型，用于测试和对比不同模型的效果。

## 如何启用

### 1. 配置开发者邀请码

在环境变量中设置 `DEVELOPER_INVITE_CODES`：

```bash
# .env 或环境变量
DEVELOPER_INVITE_CODES=dev001,dev002,dev003
```

### 2. 用户注册

- 使用开发者邀请码注册的用户自动获得开发者模式
- 使用普通邀请码（`INVITE_CODES`）注册的是普通用户
- 两种邀请码在同一个输入框输入，系统自动识别

## 可选模型列表

| 模型 | 价格 (Input/1M) | 定位 |
|------|-----------------|------|
| gpt-4o-mini | $0.15 | 经济型 |
| gpt-5-nano | $0.05 | 最便宜 |
| gpt-5-mini | $0.25 | 经济型 |
| gpt-5 | $1.25 | 标准 |
| gpt-5.2 | $1.75 | 旗舰 |
| gpt-4o | $2.50 | 标准 |
| gpt-4.1 | $2.00 | 标准 |
| o3-mini | $0.55 | 推理型 |
| o3 | $2.00 | 推理型 |
| o1 | $5.00 | 最强推理 |

## 默认模型配置

普通用户和开发者未选择模型时使用的默认配置：

| 步骤 | 默认模型 |
|------|---------|
| profile_extraction | gpt-5-nano |
| questionnaire | gpt-5-nano |
| answer_to_profile | gpt-5-nano |
| find_recommendations | gpt-5.2 |
| deep_search | gpt-5-mini |
| generate_email | gpt-5 |
| rewrite_email | gpt-5-mini |

## API 使用

### 获取用户信息和可选模型

```http
GET /api/me
```

响应（开发者用户）：
```json
{
  "success": true,
  "user": {
    "id": "xxx",
    "email": "dev@example.com",
    "developer_mode": true
  },
  "available_models": {
    "gpt-5-nano": {"name": "GPT-5 Nano", "price": "$0.05/1M", "tier": "economy"},
    "gpt-5": {"name": "GPT-5", "price": "$1.25/1M", "tier": "standard"},
    ...
  },
  "default_step_models": {
    "generate_email": "gpt-5",
    "find_recommendations": "gpt-5.2",
    ...
  }
}
```

### 调用 API 时选择模型

开发者可以在请求中添加 `model` 参数：

```http
POST /api/generate-email
Content-Type: application/json

{
  "sender": {...},
  "receiver": {...},
  "goal": "Request a coffee chat",
  "model": "gpt-5.2"
}
```

### 支持模型选择的 API

| API | 对应步骤 |
|-----|---------|
| POST /api/upload-sender-pdf | profile_extraction |
| POST /api/generate-questionnaire | questionnaire |
| POST /api/profile-from-questionnaire | answer_to_profile |
| POST /api/find-recommendations | find_recommendations |
| POST /api/generate-email | generate_email |
| POST /api/regenerate-email | rewrite_email |

## 前端集成示例

```javascript
// 1. 获取用户信息
const response = await fetch('/api/me');
const { user, available_models, default_step_models } = await response.json();

// 2. 检查是否为开发者
if (user.developer_mode) {
  // 显示模型选择器
  showModelSelector(available_models);
}

// 3. 调用 API 时传递选择的模型
async function generateEmail(sender, receiver, goal, selectedModel) {
  const body = { sender, receiver, goal };

  // 开发者模式下添加模型参数
  if (selectedModel) {
    body.model = selectedModel;
  }

  const response = await fetch('/api/generate-email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });

  return response.json();
}
```

## 数据库字段

用户表 `users` 新增字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| developer_mode | INTEGER | 0=普通用户, 1=开发者 |
| developer_mode_granted_at | TEXT | 授予时间 (ISO格式) |

## 管理开发者权限

通过 `AuthService` 方法管理：

```python
from src.services.auth_service import auth_service

# 检查用户是否为开发者
is_dev = auth_service.user_has_developer_mode(user_id)

# 手动授予开发者权限
auth_service.grant_developer_mode(user_id)

# 撤销开发者权限
auth_service.revoke_developer_mode(user_id)
```

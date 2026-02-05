# 管理员功能使用指南

## 概述

Connact.ai 管理员系统提供完整的用户管理和错误监控功能，包括：

- ✅ **用户管理**：查看所有用户、管理 Credits、查看用户详情
- ✅ **错误日志**：查看所有错误、标记已解决、错误详情分析
- ✅ **实时统计**：用户数量、活跃用户、错误统计、Credits 消耗
- ✅ **错误去重**：5分钟内相同错误自动去重，避免告警风暴
- ✅ **自动跳转**：管理员登录后自动跳转到管理后台

## 快速开始

### 1. 配置管理员邮箱

**本地开发**:
```bash
# 编辑 start_local_admin.sh
export ADMIN_EMAILS="your-email@example.com"

# 或者直接在终端设置
export ADMIN_EMAILS="admin1@example.com,admin2@example.com"

# 启动应用
bash start_local_admin.sh
```

**生产环境 (Render/Heroku)**:
```bash
# 在 Dashboard 中添加环境变量
ADMIN_EMAILS=your-email@example.com

# 多个管理员用逗号分隔
ADMIN_EMAILS=admin1@example.com,admin2@example.com,admin3@example.com
```

### 2. 访问管理后台

1. 使用管理员邮箱登录系统
2. 系统会自动跳转到 `/admin` 页面
3. 非管理员用户访问 `/admin` 会返回 403 错误

## 功能详解

### 📊 概览页面

显示系统核心指标：
- **总用户数**：注册用户总数
- **今日活跃用户**：今天登录过的用户数量
- **未解决错误**：需要处理的错误数量
- **总 Credits 消耗**：所有用户累计使用的 Apollo Credits

### 👥 用户管理

#### 查看用户列表

显示所有用户的基本信息：
- 邮箱、显示名称
- 剩余 Credits 和已使用数量
- 创建时间、最后登录时间
- 操作按钮（详情、添加 Credits）

#### 查看用户详情

点击「详情」按钮查看完整用户信息：
- 用户ID、邮箱、显示名称
- 验证状态、创建时间、最后登录
- Credits 详情（剩余、已使用、最后使用时间）
- 使用统计（保存的联系人数量、生成的邮件数量）

#### 添加 Credits

为用户手动添加 Apollo Credits：
1. 点击用户列表中的「+ Credits」按钮
2. 输入要添加的数量（必须为正整数）
3. 点击「确认添加」
4. 系统显示新的余额

**使用场景**：
- 用户反馈 Credits 用完
- 补偿用户（系统故障、误扣等）
- VIP 用户福利
- 测试账号充值

### 🐛 错误日志

#### 查看错误列表

显示所有错误记录：
- 错误ID、错误类型
- 错误信息（悬停查看完整信息）
- 请求路径（触发错误的 API 端点）
- 用户ID、发生时间
- 状态（未解决/已解决）
- 操作按钮（查看详情）

**筛选选项**：
- □ 显示已解决的错误（默认只显示未解决）
- 点击「刷新」重新加载数据

#### 查看错误详情

点击「查看」按钮查看完整错误信息：
- **错误ID**：数据库记录ID
- **错误类型**：异常类名（ValueError、ConnectionError 等）
- **错误信息**：完整的错误描述
- **请求路径**：触发错误的 URL
- **用户ID**：发生错误的用户
- **发生时间**：精确到秒
- **上下文**：JSON 格式的请求上下文（API 参数、操作类型等）
- **堆栈信息**：完整的错误追踪

#### 标记错误为已解决

在错误详情页面：
1. 查看错误详情
2. 在「解决备注」中输入解决方案或说明（可选）
3. 点击「✓ 标记为已解决」
4. 系统记录解决时间和解决人（管理员邮箱）

**最佳实践**：
```
好的备注示例：
✓ "修复了 PDF 解析逻辑，已部署到生产环境"
✓ "用户输入错误，已联系用户说明操作流程"
✓ "外部 API 暂时故障，已恢复正常"
✓ "优化了错误处理，添加了参数校验"

不好的备注示例：
✗ "已修复"（太简略，无法追溯）
✗ "不知道"（应该先调查清楚）
```

## 错误去重机制

### 工作原理

系统会自动去重 **5分钟内** 的相同错误：

**错误标识**：`错误类型:错误信息(前100字):请求路径`

**示例**：
```python
# 第一次出现：发送企业微信通知 ✅
ValueError: Invalid email format:/api/generate-email

# 5分钟内再次出现：跳过通知 ⏭️
ValueError: Invalid email format:/api/generate-email

# 5分钟后再次出现：发送企业微信通知 ✅
ValueError: Invalid email format:/api/generate-email
```

**优点**：
- 避免告警风暴（短时间内大量重复通知）
- 减少企业微信消息频率限制（最高 20条/分钟）
- 所有错误仍会保存到数据库（不会丢失）

**注意**：
- 去重只影响企业微信通知
- 所有错误都会记录到 `error_logs` 表
- 管理员仍可在后台查看所有错误

## 权限控制

### 管理员识别

系统通过邮箱判断是否为管理员：
```python
# config.py
ADMIN_EMAILS = ["admin1@example.com", "admin2@example.com"]

def is_admin(email: str) -> bool:
    return email.lower() in ADMIN_EMAILS
```

### 访问控制

| 路由 | 权限要求 | 失败处理 |
|------|---------|---------|
| `/admin` | 登录 + 管理员 | 非管理员跳转到普通页面 |
| `/api/admin/*` | 登录 + 管理员 | 返回 403 错误 |
| `/` (主页) | - | 管理员自动跳转到 /admin |

### 装饰器

```python
# 登录验证
@app.route('/api/something')
@login_required
def api_something():
    # 需要登录

# 管理员验证
@app.route('/api/admin/something')
@admin_required
def api_admin_something():
    # 需要登录 + 管理员权限
```

## API 端点

### 用户管理 API

#### GET /api/admin/users
获取所有用户列表

**响应**：
```json
{
  "success": true,
  "users": [
    {
      "user_id": "user_abc123",
      "email": "user@example.com",
      "display_name": "John Doe",
      "is_verified": true,
      "created_at": "2026-01-15T10:30:00Z",
      "last_login_at": "2026-02-06T15:20:00Z",
      "credits": {
        "apollo_credits": 5,
        "total_used": 10,
        "last_used_at": "2026-02-05T14:00:00Z"
      }
    }
  ]
}
```

#### GET /api/admin/user/{user_id}/credits
获取用户 Credits 详情

**响应**：
```json
{
  "success": true,
  "credits": {
    "apollo_credits": 5,
    "total_used": 10,
    "last_used_at": "2026-02-05T14:00:00Z"
  }
}
```

#### POST /api/admin/user/{user_id}/add-credits
添加 Credits

**请求**：
```json
{
  "amount": 10
}
```

**响应**：
```json
{
  "success": true,
  "message": "Added 10 credits",
  "new_total": 15
}
```

#### GET /api/admin/user/{user_id}/info
获取用户完整信息

**响应**：
```json
{
  "success": true,
  "user": {
    "user_id": "user_abc123",
    "email": "user@example.com",
    "display_name": "John Doe",
    "is_verified": true,
    "created_at": "2026-01-15T10:30:00Z",
    "last_login_at": "2026-02-06T15:20:00Z"
  },
  "credits": {
    "apollo_credits": 5,
    "total_used": 10,
    "last_used_at": "2026-02-05T14:00:00Z"
  },
  "usage": {
    "saved_contacts": 15,
    "generated_emails": 8
  }
}
```

### 错误日志 API

#### GET /api/admin/errors
获取错误日志列表

**查询参数**：
- `limit`: 返回数量（默认 100，最大 500）
- `offset`: 偏移量（分页）
- `show_resolved`: 是否显示已解决错误（默认 false）

**响应**：
```json
{
  "success": true,
  "errors": [
    {
      "id": 123,
      "error_type": "ValueError",
      "error_message": "Invalid email format",
      "request_path": "/api/generate-email",
      "user_id": "user_abc123",
      "context": {
        "deep_search": true,
        "goal": "networking"
      },
      "created_at": "2026-02-06T15:30:00Z",
      "resolved_at": null,
      "resolved_by": null,
      "notes": null
    }
  ],
  "total": 50,
  "limit": 100,
  "offset": 0
}
```

#### POST /api/admin/error/{error_id}/resolve
标记错误为已解决

**请求**：
```json
{
  "notes": "修复了邮箱格式验证逻辑"
}
```

**响应**：
```json
{
  "success": true,
  "message": "Error marked as resolved"
}
```

## 数据库表结构

### error_logs 表

```sql
CREATE TABLE error_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_type TEXT NOT NULL,              -- 错误类型
    error_message TEXT NOT NULL,           -- 错误信息
    request_path TEXT,                     -- 请求路径
    user_id TEXT,                          -- 用户ID
    context TEXT,                          -- JSON 格式上下文
    stack_trace TEXT,                      -- 完整堆栈
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,                 -- 解决时间
    resolved_by TEXT,                      -- 解决人邮箱
    notes TEXT                             -- 解决备注
);

-- 索引
CREATE INDEX idx_error_logs_created ON error_logs(created_at DESC);
CREATE INDEX idx_error_logs_resolved ON error_logs(resolved_at);
```

### 数据保留

**当前策略**：永久保留所有错误日志

**建议**：
- 定期归档超过 3 个月的已解决错误
- 保留最近 6 个月的所有错误
- 重要错误永久保留

**清理脚本示例**（未实现）：
```sql
-- 删除 6 个月前的已解决错误
DELETE FROM error_logs 
WHERE resolved_at IS NOT NULL 
  AND resolved_at < datetime('now', '-6 months');
```

## 安全建议

### 1. 管理员邮箱保护

```bash
# ✅ 使用强密码的邮箱账号
# ✅ 启用两步验证（Google OAuth）
# ✅ 不要在代码中硬编码管理员邮箱
# ❌ 不要使用容易猜测的邮箱（如 admin@domain.com）
```

### 2. 生产环境配置

```bash
# Render/Heroku 环境变量
ADMIN_EMAILS=your-real-email@company.com  # 使用真实邮箱
SECRET_KEY=strong-random-secret-key-here  # 强随机密钥
INVITE_ONLY=true                          # 启用邀请码保护
WECHAT_WEBHOOK_URL=https://...            # 配置错误通知
```

### 3. 定期审计

**每周检查**：
- 查看未解决错误数量
- 检查异常用户行为
- 验证 Credits 消耗是否合理

**每月检查**：
- 回顾已解决错误的备注
- 总结常见错误类型
- 优化系统稳定性

## 故障排查

### 无法访问 /admin 页面

**症状**：访问 `/admin` 跳转到普通用户页面

**解决方案**：
1. 检查环境变量是否设置：
   ```bash
   echo $ADMIN_EMAILS
   ```
2. 确认登录邮箱与 `ADMIN_EMAILS` 完全匹配（不区分大小写）
3. 重启应用使环境变量生效
4. 查看日志确认 `config.is_admin()` 返回值

### 错误日志为空

**症状**：`/api/admin/errors` 返回空列表

**可能原因**：
1. 数据库表未创建：
   ```python
   # error_notifier 会在初始化时自动创建表
   # 但如果失败会静默处理
   ```
2. 确实没有错误发生（系统运行正常）

**解决方案**：
1. 手动触发一个错误测试：
   ```bash
   curl http://localhost:5000/api/nonexistent
   ```
2. 检查数据库文件：
   ```bash
   sqlite3 data/connact.db "SELECT COUNT(*) FROM error_logs;"
   ```

### 错误通知未发送到企业微信

**症状**：错误保存到数据库，但企业微信没有收到

**检查清单**：
1. ✅ 环境变量 `WECHAT_WEBHOOK_URL` 已设置
2. ✅ Webhook URL 有效（使用 test_wechat_error_notification.py 测试）
3. ✅ 企业微信群机器人未被删除
4. ✅ 网络连接正常（服务器可以访问企业微信 API）
5. ⚠️ 可能被去重机制跳过（5分钟内相同错误）

**调试**：
```bash
# 查看应用日志
grep "ERROR_NOTIFIER" logs/app.log

# 查看跳过的错误
grep "Skipping duplicate error" logs/app.log
```

## 最佳实践

### 1. 错误处理流程

```
1. 收到企业微信通知
   ↓
2. 登录管理后台查看详情
   ↓
3. 分析错误原因和影响范围
   ↓
4. 修复问题并部署
   ↓
5. 验证修复效果
   ↓
6. 标记错误为已解决并添加备注
```

### 2. Credits 管理策略

**新用户默认**：5 个 Apollo Credits

**补充场景**：
- **系统故障补偿**：+5~10 Credits
- **活跃用户奖励**：+5 Credits/月
- **VIP 用户**：+20 Credits（一次性）
- **测试账号**：+100 Credits

**监控指标**：
- 平均每用户消耗速度
- Credits 用尽用户比例
- 未使用 Credits 的用户比例

### 3. 数据分析

定期导出数据进行分析：
```sql
-- 最活跃用户
SELECT user_id, email, total_used 
FROM users u 
JOIN user_credits c ON u.user_id = c.user_id 
ORDER BY total_used DESC 
LIMIT 10;

-- 最常见错误类型
SELECT error_type, COUNT(*) as count 
FROM error_logs 
WHERE created_at > datetime('now', '-7 days')
GROUP BY error_type 
ORDER BY count DESC;

-- 错误趋势（按天）
SELECT DATE(created_at) as date, COUNT(*) as errors
FROM error_logs
WHERE created_at > datetime('now', '-30 days')
GROUP BY DATE(created_at)
ORDER BY date;
```

## 相关文件

- `config.py` - 管理员配置
- `app.py` - 管理员路由和 API
- `templates/admin.html` - 管理员界面
- `src/services/error_notifier.py` - 错误通知服务
- `admin_credits.py` - CLI 工具（备用）
- `start_local_admin.sh` - 本地启动脚本

## 更新日志

- **2026-02-06**: 
  - ✅ 创建完整的管理员系统
  - ✅ 添加错误去重机制（5分钟窗口）
  - ✅ 错误日志自动保存到数据库
  - ✅ 实现用户管理和 Credits 添加功能
  - ✅ 管理员自动跳转到后台
  - ✅ 创建使用文档

## 支持

如有问题或建议：
1. 查看本文档的故障排查章节
2. 检查应用日志 `logs/app.log`
3. 查看企业微信错误通知
4. 联系开发团队

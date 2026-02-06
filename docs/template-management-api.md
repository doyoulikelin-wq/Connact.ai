# 邮件模板管理 API 文档

## 概述

邮件模板管理功能允许用户保存、管理和复用邮件模板。避免重复上传模板，提升使用效率。

## 数据模型

### Template 对象

```json
{
  "id": "tmpl_a1b2c3d4e5f6",
  "user_id": "user_123456",
  "name": "金融行业通用模板",
  "content": "Hi {name},\n\nMy name is...",
  "description": "适用于投行、咨询等金融行业的冷邮件模板",
  "use_count": 15,
  "last_used_at": "2026-02-06T10:30:00Z",
  "created_at": "2026-01-15T08:00:00Z",
  "updated_at": "2026-02-06T10:30:00Z"
}
```

## API 端点

### 1. 保存新模板

**请求**：
```http
POST /api/templates
Content-Type: application/json

{
  "name": "金融行业通用模板",
  "content": "Hi {name},\n\nMy name is...",
  "description": "适用于投行、咨询等金融行业的冷邮件模板"
}
```

**响应**：
```json
{
  "success": true,
  "template_id": "tmpl_a1b2c3d4e5f6"
}
```

### 2. 获取用户所有模板

**请求**：
```http
GET /api/templates?limit=50&offset=0
```

**响应**：
```json
{
  "success": true,
  "templates": [
    {
      "id": "tmpl_a1b2c3d4e5f6",
      "name": "金融行业通用模板",
      "content": "Hi {name}...",
      "description": "适用于投行、咨询等金融行业",
      "use_count": 15,
      "last_used_at": "2026-02-06T10:30:00Z",
      "created_at": "2026-01-15T08:00:00Z",
      "updated_at": "2026-02-06T10:30:00Z"
    },
    ...
  ]
}
```

### 3. 获取特定模板

**请求**：
```http
GET /api/templates/tmpl_a1b2c3d4e5f6
```

**响应**：
```json
{
  "success": true,
  "template": {
    "id": "tmpl_a1b2c3d4e5f6",
    "name": "金融行业通用模板",
    "content": "Hi {name}...",
    ...
  }
}
```

### 4. 更新模板

**请求**：
```http
PUT /api/templates/tmpl_a1b2c3d4e5f6
Content-Type: application/json

{
  "name": "金融行业通用模板（已优化）",
  "content": "新的模板内容...",
  "description": "更新后的描述"
}
```

**响应**：
```json
{
  "success": true
}
```

**注意**：所有字段都是可选的，只更新提供的字段。

### 5. 删除模板

**请求**：
```http
DELETE /api/templates/tmpl_a1b2c3d4e5f6
```

**响应**：
```json
{
  "success": true
}
```

### 6. 使用模板生成邮件

**请求（方式1：使用 template_id）**：
```http
POST /api/generate-email
Content-Type: application/json

{
  "template_id": "tmpl_a1b2c3d4e5f6",
  "sender": { ... },
  "receiver": { ... },
  "goal": "..."
}
```

**请求（方式2：直接提供模板内容）**：
```http
POST /api/generate-email
Content-Type: application/json

{
  "template": "Hi {name}...",
  "sender": { ... },
  "receiver": { ... },
  "goal": "..."
}
```

**响应**：
```json
{
  "success": true,
  "email": "Subject: ...\n\nHi John...",
  "template_used": {
    "id": "tmpl_a1b2c3d4e5f6",
    "name": "金融行业通用模板"
  }
}
```

## 前端实现建议

### 1. 模板列表界面

```html
<!-- 模板选择下拉框 -->
<select id="template-selector">
  <option value="">不使用模板</option>
  <option value="tmpl_123">金融行业通用模板 (用过 15 次)</option>
  <option value="tmpl_456">技术岗位模板 (用过 8 次)</option>
  <option value="custom">+ 上传新模板</option>
</select>
```

### 2. 模板管理页面

```javascript
// 加载模板列表
async function loadTemplates() {
  const response = await fetch('/api/templates');
  const data = await response.json();
  
  if (data.success) {
    renderTemplates(data.templates);
  }
}

// 渲染模板卡片
function renderTemplates(templates) {
  const container = document.getElementById('templates-container');
  container.innerHTML = templates.map(template => `
    <div class="template-card">
      <h3>${escapeHtml(template.name)}</h3>
      <p>${escapeHtml(template.description)}</p>
      <div class="template-stats">
        <span>使用 ${template.use_count} 次</span>
        <span>最后使用：${formatDate(template.last_used_at)}</span>
      </div>
      <div class="template-actions">
        <button onclick="useTemplate('${template.id}')">使用</button>
        <button onclick="editTemplate('${template.id}')">编辑</button>
        <button onclick="deleteTemplate('${template.id}')">删除</button>
      </div>
    </div>
  `).join('');
}

// 保存新模板
async function saveTemplate(name, content, description) {
  const response = await fetch('/api/templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content, description })
  });
  
  const data = await response.json();
  if (data.success) {
    alert('模板已保存！');
    loadTemplates(); // 刷新列表
  }
}

// 使用模板生成邮件
async function generateEmailWithTemplate(templateId) {
  const response = await fetch('/api/generate-email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      template_id: templateId,
      sender: getSenderProfile(),
      receiver: getReceiverProfile(),
      goal: getGoal()
    })
  });
  
  const data = await response.json();
  if (data.success) {
    displayEmail(data.email);
    if (data.template_used) {
      console.log(`使用了模板：${data.template_used.name}`);
    }
  }
}
```

### 3. 上传模板时自动保存

```javascript
// 用户上传模板文本时
function onTemplateUpload(templateContent) {
  // 显示保存对话框
  showSaveTemplateDialog(templateContent);
}

function showSaveTemplateDialog(content) {
  const name = prompt('请为模板命名：', '我的模板');
  const description = prompt('描述（可选）：', '');
  
  if (name) {
    saveTemplate(name, content, description);
  }
}
```

### 4. 邮件生成页面集成

```javascript
// 在生成邮件页面
let currentTemplate = null;

// 1. 显示模板选择器
function initTemplateSelector() {
  const selector = document.getElementById('template-selector');
  
  // 加载用户的模板
  fetch('/api/templates')
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        data.templates.forEach(template => {
          const option = document.createElement('option');
          option.value = template.id;
          option.textContent = `${template.name} (用过 ${template.use_count} 次)`;
          selector.appendChild(option);
        });
      }
    });
  
  // 选择模板时
  selector.addEventListener('change', function() {
    if (this.value === 'custom') {
      // 显示上传模板界面
      showTemplateUpload();
    } else if (this.value) {
      // 加载选中的模板
      loadTemplate(this.value);
    } else {
      currentTemplate = null;
    }
  });
}

// 2. 生成邮件时使用模板
async function generateEmail() {
  const requestData = {
    sender: getSenderProfile(),
    receiver: getReceiverProfile(),
    goal: getGoal()
  };
  
  // 如果选择了模板，添加 template_id
  if (currentTemplate) {
    requestData.template_id = currentTemplate.id;
  }
  
  const response = await fetch('/api/generate-email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestData)
  });
  
  // 处理响应...
}
```

## Activity 记录

使用模板时，activity 中会记录：

```json
{
  "event_type": "email_generated",
  "payload": {
    "goal": "...",
    "template": "实际使用的模板内容",
    "template_id": "tmpl_a1b2c3d4e5f6",
    "template_name": "金融行业通用模板",
    "receiver": { ... },
    "email_text": "生成的邮件内容"
  }
}
```

## 错误处理

### 常见错误码

- `401 Unauthorized` - 未登录
- `403 Forbidden` - 尝试访问/修改他人的模板
- `404 Not Found` - 模板不存在
- `400 Bad Request` - 请求参数错误（如缺少必填字段）
- `500 Internal Server Error` - 服务器错误

### 示例错误响应

```json
{
  "error": "Template name is required"
}
```

## 最佳实践

1. **命名规范**：使用清晰描述性的名称，如"金融行业-投行岗位"而非"模板1"
2. **添加描述**：说明模板适用场景、目标人群等，方便日后选择
3. **定期清理**：删除不再使用的旧模板，保持列表整洁
4. **版本管理**：重要模板修改前可以复制一份作为备份
5. **使用统计**：关注 `use_count`，了解哪些模板最有效

## 数据迁移

如果用户已有大量模板文本文件，可以批量导入：

```python
import requests

def batch_import_templates(templates):
    """批量导入模板"""
    for template in templates:
        response = requests.post('http://localhost:5000/api/templates', 
            json={
                'name': template['name'],
                'content': template['content'],
                'description': template['description']
            },
            headers={'Cookie': 'session=...'} # 需要登录
        )
        print(f"导入 {template['name']}: {response.json()}")

# 使用示例
templates = [
    {
        'name': '金融行业通用模板',
        'content': 'Hi {name}...',
        'description': '适用于投行、咨询'
    },
    # ... 更多模板
]

batch_import_templates(templates)
```

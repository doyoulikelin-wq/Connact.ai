# 前端集成：邮件模板管理功能

## 概述

用户现在可以保存、管理和复用邮件模板。前端需要添加以下功能：

1. **模板选择器**：在生成邮件页面添加模板下拉选择
2. **模板保存**：用户上传模板时提供保存选项
3. **模板管理页面**（可选）：查看、编辑、删除已保存模板

## 必须实现的核心功能

### 1. 在邮件生成页面添加模板选择器

**位置**：`templates/index_v2.html` 或主邮件生成界面

**HTML 结构**：

```html
<!-- 在目标人物信息 (Receiver) 和生成按钮之间添加 -->
<div class="form-group">
    <label>📝 使用邮件模板（可选）</label>
    <select id="template-selector" class="form-control">
        <option value="">不使用模板（智能生成）</option>
        <!-- 动态加载用户的模板 -->
    </select>
    <small class="text-muted">
        选择已保存的模板，或点击"自定义模板"上传新模板
    </small>
</div>

<!-- 自定义模板上传区域（隐藏，需要时显示） -->
<div id="custom-template-area" style="display: none;">
    <label>自定义模板内容</label>
    <textarea id="custom-template-content" rows="6" class="form-control"
              placeholder="粘贴或输入模板内容..."></textarea>
    <button class="btn btn-sm btn-success" onclick="saveCurrentTemplate()">
        💾 保存此模板
    </button>
</div>
```

**JavaScript 实现**：

```javascript
// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    initTemplateSelector();
});

// 初始化模板选择器
async function initTemplateSelector() {
    const selector = document.getElementById('template-selector');
    
    try {
        const response = await fetch('/api/templates');
        const data = await response.json();
        
        if (data.success && data.templates.length > 0) {
            // 添加用户的模板选项
            data.templates.forEach(template => {
                const option = document.createElement('option');
                option.value = template.id;
                option.textContent = `${template.name} (用过 ${template.use_count} 次)`;
                option.dataset.content = template.content;
                selector.appendChild(option);
            });
        }
        
        // 添加"自定义模板"选项
        const customOption = document.createElement('option');
        customOption.value = 'custom';
        customOption.textContent = '➕ 自定义模板...';
        selector.appendChild(customOption);
        
        // 监听选择变化
        selector.addEventListener('change', onTemplateSelect);
        
    } catch (error) {
        console.error('加载模板失败:', error);
    }
}

// 模板选择改变时
function onTemplateSelect() {
    const selector = document.getElementById('template-selector');
    const customArea = document.getElementById('custom-template-area');
    const customContent = document.getElementById('custom-template-content');
    
    if (selector.value === 'custom') {
        // 显示自定义模板输入区
        customArea.style.display = 'block';
        customContent.value = '';
    } else if (selector.value) {
        // 选择了已保存的模板
        customArea.style.display = 'none';
        const selectedOption = selector.options[selector.selectedIndex];
        console.log('已选择模板:', selectedOption.textContent);
    } else {
        // 不使用模板
        customArea.style.display = 'none';
    }
}

// 保存当前自定义模板
async function saveCurrentTemplate() {
    const content = document.getElementById('custom-template-content').value.trim();
    
    if (!content) {
        alert('请输入模板内容');
        return;
    }
    
    const name = prompt('请为模板命名:', '我的模板');
    if (!name) return;
    
    const description = prompt('描述（可选，帮助日后识别）:', '');
    
    try {
        const response = await fetch('/api/templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, content, description })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('✓ 模板已保存！');
            // 重新加载模板列表
            await initTemplateSelector();
            // 自动选择新保存的模板
            document.getElementById('template-selector').value = data.template_id;
        } else {
            alert('保存失败: ' + (data.error || '未知错误'));
        }
    } catch (error) {
        console.error('保存模板失败:', error);
        alert('保存失败: ' + error.message);
    }
}
```

### 2. 修改邮件生成函数

**修改 `generateEmail()` 函数**：

```javascript
async function generateEmail() {
    const selector = document.getElementById('template-selector');
    const customContent = document.getElementById('custom-template-content');
    
    // 构建请求数据
    const requestData = {
        sender: getCurrentSenderProfile(),
        receiver: getCurrentReceiverProfile(),
        goal: document.getElementById('goal-input').value
    };
    
    // 处理模板
    if (selector.value === 'custom') {
        // 使用自定义模板（直接传内容）
        const content = customContent.value.trim();
        if (content) {
            requestData.template = content;
        }
    } else if (selector.value) {
        // 使用已保存的模板（传 template_id）
        requestData.template_id = selector.value;
    }
    // 否则不使用模板（智能生成）
    
    try {
        const response = await fetch('/api/generate-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });
        
        const data = await response.json();
        
        if (data.success) {
            displayGeneratedEmail(data.email);
            
            // 如果使用了模板，显示提示
            if (data.template_used) {
                showNotification(`使用了模板：${data.template_used.name}`);
            }
        } else {
            alert('生成失败: ' + (data.error || '未知错误'));
        }
    } catch (error) {
        console.error('生成邮件失败:', error);
        alert('生成失败: ' + error.message);
    }
}
```

## 可选：模板管理页面

如果希望提供完整的模板管理界面，可以添加以下内容：

### 模板列表页面

```html
<!-- 在主导航添加链接 -->
<a href="#templates">我的模板</a>

<!-- 模板管理页面 -->
<div id="templates-page" style="display: none;">
    <h2>📝 我的邮件模板</h2>
    <button class="btn btn-primary" onclick="showNewTemplateDialog()">
        ➕ 新建模板
    </button>
    
    <div id="templates-list" class="template-cards">
        <!-- 动态加载模板卡片 -->
    </div>
</div>
```

```javascript
// 加载并渲染模板列表
async function loadTemplatesList() {
    const container = document.getElementById('templates-list');
    container.innerHTML = '<div class="loading">加载中...</div>';
    
    try {
        const response = await fetch('/api/templates');
        const data = await response.json();
        
        if (data.success) {
            if (data.templates.length === 0) {
                container.innerHTML = '<p class="text-muted">还没有保存任何模板</p>';
                return;
            }
            
            container.innerHTML = data.templates.map(template => `
                <div class="template-card" data-id="${template.id}">
                    <div class="template-header">
                        <h3>${escapeHtml(template.name)}</h3>
                        <div class="template-actions">
                            <button onclick="useTemplate('${template.id}')">使用</button>
                            <button onclick="editTemplate('${template.id}')">编辑</button>
                            <button onclick="deleteTemplate('${template.id}')">删除</button>
                        </div>
                    </div>
                    <p class="template-description">${escapeHtml(template.description || '无描述')}</p>
                    <div class="template-stats">
                        <span>📊 使用 ${template.use_count} 次</span>
                        <span>🕒 ${formatDate(template.last_used_at || template.created_at)}</span>
                    </div>
                    <pre class="template-content">${escapeHtml(template.content.substring(0, 200))}${template.content.length > 200 ? '...' : ''}</pre>
                </div>
            `).join('');
        }
    } catch (error) {
        container.innerHTML = '<p class="text-danger">加载失败: ' + error.message + '</p>';
    }
}

// 使用模板（跳转到邮件生成页并预选模板）
function useTemplate(templateId) {
    // 跳转到邮件生成页面
    showPage('email-generator');
    // 预选这个模板
    document.getElementById('template-selector').value = templateId;
    onTemplateSelect();
}

// 编辑模板
async function editTemplate(templateId) {
    try {
        const response = await fetch(`/api/templates/${templateId}`);
        const data = await response.json();
        
        if (data.success) {
            const template = data.template;
            const name = prompt('模板名称:', template.name);
            if (name === null) return;
            
            const description = prompt('描述:', template.description);
            const content = prompt('内容 (输入 skip 跳过修改):', template.content.substring(0, 100));
            
            const updates = { name, description };
            if (content !== 'skip') {
                updates.content = content;
            }
            
            const updateResponse = await fetch(`/api/templates/${templateId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
            
            const updateData = await updateResponse.json();
            if (updateData.success) {
                alert('✓ 模板已更新');
                loadTemplatesList();
            }
        }
    } catch (error) {
        alert('编辑失败: ' + error.message);
    }
}

// 删除模板
async function deleteTemplate(templateId) {
    if (!confirm('确定要删除这个模板吗？此操作无法撤销。')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/templates/${templateId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        if (data.success) {
            alert('✓ 模板已删除');
            loadTemplatesList();
        }
    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}
```

### CSS 样式建议

```css
.template-card {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
    background: white;
    transition: box-shadow 0.2s;
}

.template-card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.template-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.template-header h3 {
    margin: 0;
    font-size: 18px;
    color: #333;
}

.template-actions button {
    margin-left: 8px;
    padding: 6px 12px;
    border: 1px solid #ddd;
    background: white;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
}

.template-actions button:hover {
    background: #f5f5f5;
}

.template-description {
    color: #666;
    margin-bottom: 12px;
    font-size: 14px;
}

.template-stats {
    display: flex;
    gap: 16px;
    margin-bottom: 12px;
    font-size: 13px;
    color: #888;
}

.template-content {
    background: #f8f9fa;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 12px;
    font-size: 13px;
    font-family: 'Monaco', 'Courier New', monospace;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
}

#custom-template-area {
    margin-top: 12px;
    padding: 16px;
    background: #f8f9fa;
    border-radius: 8px;
}

#custom-template-area textarea {
    margin-bottom: 12px;
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 13px;
}
```

## 测试清单

实现后请测试以下场景：

- [ ] 页面加载时模板选择器正常显示
- [ ] 可以看到所有已保存的模板（按更新时间排序）
- [ ] 选择"自定义模板"时显示输入区域
- [ ] 可以保存新模板（名称、内容、描述）
- [ ] 使用已保存模板生成邮件（通过 template_id）
- [ ] 使用自定义模板生成邮件（通过 template）
- [ ] 不选择模板时智能生成（不传 template 参数）
- [ ] 模板使用后计数增加（需要刷新列表验证）
- [ ] 可以编辑已保存的模板
- [ ] 可以删除模板
- [ ] 只能访问自己的模板（权限验证）

## 后续优化建议

1. **模板预览**：点击模板卡片时弹窗显示完整内容
2. **搜索过滤**：模板多时添加搜索框
3. **分类标签**：为模板添加标签（如"金融"、"技术"）
4. **导入导出**：支持批量导入/导出模板（JSON 格式）
5. **模板变量**：在编辑器中提示可用变量（如 {name}, {company}）
6. **版本历史**：保存模板修改历史，可以回滚
7. **共享模板**：允许用户分享模板给团队成员
8. **模板统计**：显示每个模板的成功率、回复率等

## 需要协助？

如有任何问题或需要进一步的技术支持，请查看：
- API 文档：`docs/template-management-api.md`
- 开发日志：`devlog.md` (2026-02-06 条目)

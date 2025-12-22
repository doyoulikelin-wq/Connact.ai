# Debug Log（调试日志）

本文档记录项目开发过程中遇到的重要 Bug 及其解决方案，供后续开发参考。

---

## 2025-12-23: Professional 模式目标选择失效

### 问题描述

**症状**：
- Professional 模式下，Find Targets 返回推荐列表后，用户无法点击选择任何目标
- View 按钮点击后没有反应，不显示详情弹窗
- Quick Start 模式下相同功能正常工作

**影响范围**：Professional 模式的核心流程完全不可用

### 根因分析

问题出在 `findProTargets()` 函数中的代码执行顺序：

```javascript
// 原始代码（有 Bug）
if (data.success && data.recommendations && data.recommendations.length > 0) {
    state.recommendations = data.recommendations;  // 1️⃣ 设置 state
    
    // ... 其他代码 ...
    
    goToStep(3);
    
    // 2️⃣ 模拟点击 "no" 按钮
    document.getElementById('target-choice').querySelector('[data-value="no"]').click();
    
    // 3️⃣ 渲染推荐列表
    renderRecommendations(data.recommendations);
}
```

**问题链条**：

1. 代码先设置 `state.recommendations = data.recommendations`
2. 然后调用 `.click()` 模拟点击 "no" 按钮
3. 点击 "no" 按钮触发事件处理器，其中调用了 `resetRecommendationState()`
4. `resetRecommendationState()` 会清空 `state.recommendations = []` 和 `state.selectedTargets = []`
5. 虽然最后调用 `renderRecommendations(data.recommendations)` 用局部变量渲染了 UI，但 `state.recommendations` 已经是空数组

**后果**：

```javascript
// toggleRecommendation 和 openProfileModal 都依赖 state.recommendations
function toggleRecommendation(index) {
    const rec = state.recommendations[index];  // ❌ 这里 state.recommendations 是空的！
    // ...
}

function openProfileModal(index) {
    const rec = state.recommendations[index];  // ❌ 同样是空的！
    if (!rec) return;  // 直接返回，什么都不做
    // ...
}
```

### 解决方案

将 `state.recommendations` 的赋值移到 `.click()` 事件之后：

```javascript
// 修复后的代码
if (data.success && data.recommendations && data.recommendations.length > 0) {
    const recommendations = data.recommendations;  // 先保存到局部变量
    
    // ... 其他代码 ...
    
    goToStep(3);
    
    // click() 会触发 resetRecommendationState() 清空 state
    document.getElementById('target-choice').querySelector('[data-value="no"]').click();
    
    // ✅ 在 click() 之后重新设置 state.recommendations
    state.recommendations = recommendations;
    renderRecommendations(recommendations);
}
```

### 经验教训与规避措施

#### 1. 理解事件副作用

**问题模式**：模拟 DOM 事件（如 `.click()`）可能触发意想不到的副作用函数。

**规避方法**：
- 在调用 `.click()` 或其他 DOM 事件模拟前，检查事件处理器中的所有逻辑
- 特别注意"重置"类函数（如 `resetXxxState()`），它们通常会清空全局状态
- 考虑是否真的需要模拟点击，或者可以直接调用所需的 UI 更新函数

#### 2. 全局状态与局部变量的时序问题

**问题模式**：
```javascript
state.data = apiData;        // 设置全局状态
someFunction();              // 这个函数可能清空 state.data
renderUI(apiData);           // UI 用的是局部变量，看起来正常
// 但后续交互依赖 state.data，已经被清空了
```

**规避方法**：
- 确保全局状态的最终赋值在所有可能修改它的操作之后
- 或者在渲染 UI 时同时更新状态，保持一致性：
  ```javascript
  state.data = apiData;
  renderUI(state.data);  // 使用 state.data 而不是 apiData
  ```

#### 3. 测试多流程入口

**问题模式**：同一个功能有多个入口（如 Quick Start 和 Professional 模式都能找目标），但只测试了其中一个。

**规避方法**：
- 每次修改共享组件时，测试所有使用该组件的流程
- 建立测试清单，列出所有需要验证的入口路径
- 本项目的关键路径：
  - [ ] Quick Start → Find Matches → 选择目标 → 生成邮件
  - [ ] Professional → Find Targets → 选择目标 → 生成邮件
  - [ ] 手动输入目标 → 生成邮件

#### 4. 调试技巧

当遇到"UI 显示正常但交互无效"的问题时：

1. **检查状态一致性**：在浏览器控制台打印关键状态变量
   ```javascript
   console.log('state.recommendations:', state.recommendations);
   console.log('state.selectedTargets:', state.selectedTargets);
   ```

2. **追踪状态变化**：临时在状态修改处加日志
   ```javascript
   function resetRecommendationState() {
       console.log('⚠️ resetRecommendationState called');
       console.trace();  // 打印调用栈
       // ...
   }
   ```

3. **对比工作流程与失败流程**：找出两者代码路径的差异

### 相关文件

- `templates/index_v2.html`
  - `findProTargets()` 函数（约 line 2837）
  - `resetRecommendationState()` 函数（约 line 4737）
  - `toggleRecommendation()` 函数（约 line 3907）
  - `openProfileModal()` 函数（约 line 3151）

---

## 模板：Bug 记录格式

```markdown
## YYYY-MM-DD: [Bug 标题]

### 问题描述
- 症状：用户看到什么？
- 影响范围：哪些功能受影响？

### 根因分析
- 问题出在哪里？
- 为什么会发生？

### 解决方案
- 如何修复？
- 代码改动是什么？

### 经验教训与规避措施
- 以后如何避免类似问题？

### 相关文件
- 涉及哪些文件和函数？
```

# Apollo API 测试指南（Credit 保护版）

## ⚠️ CREDIT 使用警告

**你的计划**: Apollo Basic Plan
- **Monthly Credits**: 75 credits
- **Email Unlock**: ~1 credit per person
- **Phone Unlock**: ~1 credit per person (需要 webhook)
- **Search API**: 不消耗 credits ✅

## 已测试验证的功能

### ✅ People Search API (已验证可用)
- **状态**: 完全可用，不消耗 credits
- **测试结果**:
  - Software Engineer (SF): 96,266 结果
  - Investment Banking Analyst (NY): 9,743 结果
  - Engineering Manager (Senior): 2,684 结果
- **脚本**: `test_apollo_simple.py` (已禁用 Enrichment 部分)

### ✅ People Enrichment API (已验证可用)
- **状态**: 完全可用，消耗 credits
- **测试结果**: Elon Musk 邮箱解锁成功 (referralprogram@tesla.com)
- **脚本**: `test_apollo_quick.py` (单个测试，安全)

### ✅ Organization Search API (已验证可用)
- **状态**: 完全可用，消耗 credits
- **测试结果**: Tesla 公司信息获取成功

## 安全测试流程

### 方案 1: 只测试搜索（推荐，0 credits）
```bash
python test_apollo_simple.py
```
- 测试 People Search 各种过滤器
- 不会消耗任何 credits
- 验证搜索结果质量

### 方案 2: 完整流程测试（需要确认，~1 credit）
```bash
python test_apollo_e2e.py
```
- 会提示确认再执行 Enrichment
- 只测试 1 个联系人
- 演示完整的 Search → Enrich 流程

### 方案 3: 单个已知联系人测试（安全，~1 credit）
```bash
python test_apollo_quick.py
```
- 测试 Elon Musk（已知有效）
- 消耗 1 credit

## ⛔ 已禁用的危险脚本

这些脚本可能会消耗大量 credits，已经被禁用：

- `test_apollo_search_to_enrich.py` - 一次测试 10+ 个联系人 (已禁用)
- `test_apollo_bulk.py` - 批量测试 (如果存在，不要运行)

## 测试总结

### 已确认可用的 API
1. **People Search** (`/mixed_people/api_search`)
   - ✅ 可用
   - ✅ 不消耗 credits
   - ✅ 强大的过滤器
   - ✅ 返回 Apollo ID（可用于 Enrichment）

2. **People Enrichment** (`/people/match`)
   - ✅ 可用
   - ⚠️ 消耗 credits (~1/人)
   - ✅ 解锁邮箱成功

3. **Bulk Enrichment** (`/people/bulk_match`)
   - ✅ 可用（基于文档）
   - ⚠️ 消耗 credits (~1/人)
   - ⚠️ 最多 10 人/请求

## 推荐架构方案

### 方案 A: Apollo 全流程（推荐）✅
```
用户输入 preferences
    ↓
Apollo People Search (0 credits)
    ↓
获取候选人列表 + Apollo IDs
    ↓
用户选择 N 个候选人
    ↓
Apollo Bulk Enrichment (N credits)
    ↓
获取 N 个邮箱
    ↓
生成个性化邮件
```

**优势**:
- 单一数据源，数据质量高
- Search 不消耗 credits，可以多次尝试
- 只在用户确认后才解锁邮箱
- 批量 Enrichment 效率高

**Credit 使用**:
- 搜索阶段: 0 credits
- 每封邮件: 1 credit (解锁收件人邮箱)
- **月度预算**: 75 credits = 75 封冷启动邮件

### 方案 B: SerpAPI + Apollo (备选)
```
SerpAPI 搜索 LinkedIn (需要 SerpAPI key)
    ↓
获取候选人列表
    ↓
用户选择
    ↓
Apollo Enrichment 解锁邮箱 (N credits)
```

**优势**:
- 保持现有 SerpAPI 逻辑
- Apollo 只用于邮箱解锁

**劣势**:
- 依赖两个服务
- SerpAPI 额外成本

## 下一步建议

### 1. 测试 People Search ID enrichment（推荐）
```bash
python test_apollo_e2e.py
# 输入 'yes' 确认，只测试 1 个联系人
```

### 2. 集成到现有流程
修改 `src/email_agent.py`:
- 添加 `_search_people_via_apollo()` 函数
- 修改 `find_target_recommendations()` 优先级
- 在用户选择候选人后调用批量解锁

### 3. 前端增加 Credit 显示
在 `templates/index_v2.html` 显示:
- 剩余 credits
- 本次操作将消耗的 credits
- 确认按钮

## Credit 管理最佳实践

1. **搜索阶段**: 尽可能多次尝试（0 credits）
2. **预览阶段**: 只显示基本信息（name, title, company）
3. **确认阶段**: 用户明确选择后再解锁邮箱
4. **批量处理**: 用 Bulk Enrichment API（最多 10 人/次）
5. **错误处理**: 解锁失败时不重试（避免浪费 credits）

## 问题排查

### Q: Enrichment 返回空结果？
A: 可能原因：
- Apollo ID 无效（从 Search 获取确保有效）
- 该联系人没有邮箱数据
- Credit 余额不足

### Q: 如何查看剩余 credits？
A: Apollo 官网 Dashboard: https://app.apollo.io/#/settings/credits

### Q: Credit 何时重置？
A: 每月账单日重置（Basic Plan: $59/月）

## 安全检查清单

在运行任何测试前：
- [ ] 确认脚本只测试 1-2 个联系人
- [ ] 查看是否有用户确认提示
- [ ] 检查是否有 "WARNING: will consume credits" 提示
- [ ] 确认不在循环中调用 Enrichment
- [ ] 生产环境添加 rate limiting

---

**最后更新**: 2026-02-06
**测试状态**: ✅ People Search 可用 | ✅ Enrichment 可用 | ⚠️ Credit 保护已启用

# 已废弃的测试文件

以下测试文件已过时，对应的功能已被撤销。保留仅供技术参考。

## Apollo + Moonshot 组合测试（2026-02-06 已废弃）

### 废弃原因
Apollo Basic Plan 的姓名混淆（last_name_obfuscated）导致 Moonshot 无法精确匹配 LinkedIn URLs。组合方案不可行，已恢复使用 SerpAPI。

### 相关文件

#### 1. `test_apollo_moonshot_combo.py`
- **状态**: ❌ 已废弃
- **功能**: 测试 Apollo Search + Moonshot URL 查找组合
- **问题**: 100% 返回率但所有 URLs 都不存在（格式正确但链接无效）
- **教训**: 测试"成功率"需验证实际结果，非只检查格式

#### 2. `test_moonshot_real_search.py`
- **状态**: ❌ 已废弃
- **功能**: 测试 Moonshot 真实搜索功能（$web_search）
- **测试案例**: Nathan Mo***l（混淆姓名）
- **结果**: NOT_FOUND（证明混淆姓名无法精确匹配）
- **技术验证**: ✅ Moonshot $web_search 实现正确

#### 3. `test_moonshot_full_name.py`
- **状态**: ❌ 已废弃（但技术正确）
- **功能**: 验证完整姓名时 Moonshot 可以找到真实 URLs
- **测试案例**: 
  - Andrew Ng → ✅ https://www.linkedin.com/in/andrewyng
  - Nathan Mollica → ✅ 成功找到真实 URL
- **结论**: Moonshot 功能正常，但需要完整姓名（Apollo Basic Plan 无法提供）

#### 4. `test_integration.py`
- **状态**: ⚠️ 部分过时
- **问题**: 基于 Moonshot v1 实现（仅 LLM 推测，非真实搜索）
- **需更新**: 如果要继续使用，需基于 v2 实现重写

### 保留的服务代码（技术正确但未使用）

#### `src/services/moonshot_service.py`
- **状态**: ✅ 技术实现正确（v2 使用 $web_search）
- **未使用原因**: Apollo 姓名混淆问题
- **保留价值**: 如果有其他完整姓名来源，可以复用

#### `src/services/apollo_service.py`
- **状态**: ✅ 部分功能仍在使用
- **保留功能**: `enrich_person()` 用于邮件查找（1 credit/人）
- **废弃功能**: `search_people_v2()` 不再用于候选人搜索

### 架构决策记录

```
日期: 2026-02-06
决策: 撤销 Apollo + Moonshot 组合搜索方案
原因: Apollo Basic Plan 混淆姓名，Moonshot 需要完整姓名
替代方案: SerpAPI (候选人搜索) + Apollo Enrichment (邮件查找)
关键洞察: API 限制（Basic Plan）往往是不可逾越的障碍
```

### 技术栈最终架构

```
候选人搜索流程:
1. SerpAPI（PRIMARY）
   ↓ 返回真实 LinkedIn profiles
2. 提取候选人信息
   ↓
3. (可选) Apollo Enrichment
   ↓ 解锁完整姓名 + 邮箱（1 credit/人）
4. 返回候选人列表

废弃的流程:
❌ Apollo Search → 混淆姓名 → Moonshot URL 查找 → 错误 URLs
```

### 参考文档
- [devlog.md](devlog.md): 完整变更记录
- [AGENTS.md](AGENTS.md): 项目架构和"两个核心任务"理念
- Moonshot 文档: https://platform.moonshot.cn/docs/guide/use-web-search
- Apollo API 文档: https://apolloio.github.io/apollo-api-docs/

---

**注意**: 不要删除这些测试文件。它们展示了重要的技术验证过程和失败案例，对未来决策有参考价值。

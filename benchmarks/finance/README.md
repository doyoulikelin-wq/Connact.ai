# Finance Benchmark (v0)

这个目录提供一个可复现、可扩展的 finance benchmark 起步包，用来评测本项目的两个核心能力：

1) 找人：`POST /api/find-recommendations`
2) 生成邮件：`POST /api/generate-email`

## 文件说明

- `benchmarks/finance/schema_v0.json`：单条样本（case）的 JSON Schema（用于约束字段与演进）。
- `benchmarks/finance/finance_v0.json`：10 条 v0 样本（**完全合成**，用于演示格式与标注方式）。
- `benchmarks/finance/rubric_v0.md`：人工评测 rubric（维度 + 失败标签）。
- `benchmarks/finance/anonymization_and_labeling_template.md`：把真实用户输入转换成 benchmark case 的匿名化与标注模板。

## 重要说明（请先读）

- v0 样本里的名字/机构/链接均为**虚构占位**（如 `example.com`），不用于衡量真实线上检索效果。
- 如果你要评测“搜人”能力并且希望有稳定的“预期输出”，建议：
  - 对证据做快照：保存关键摘录 + URL + 时间戳，或
  - 使用固定候选池（candidate pool）进行闭卷评测（更可复现）。

## 如何扩充为真实 benchmark（推荐路径）

1) 先用 `finance_v0.json` 跑通团队的“填表/标注/打分”流程（哪怕先不跑模型）。
2) 用 `anonymization_and_labeling_template.md` 把真实样本逐条替换进来（每条样本都尽量带可追溯证据）。
3) 每次迭代只改动一种东西：输入表单、提示词、排序规则或输出格式；然后对比新旧 run 的评分与失败标签分布。


# Finance Benchmark (v0.1)

这个目录提供一个可复现、可扩展的 finance benchmark 起步包，用来评测本项目的两个核心能力：

1) 找人：`POST /api/find-recommendations`
2) 生成邮件：`POST /api/generate-email`

## 文件说明

- `benchmarks/finance/schema_v0.json`：单条样本（case）的 JSON Schema（v0.1，包含更细的 finance/banker 结构化 context 字段）。
- `benchmarks/finance/finance_v0.json`：10 条 v0 样本（**完全合成**，用于演示格式与标注方式；每条包含 `version: 0.1`）。
- `benchmarks/finance/rubric_v0.md`：人工评测 rubric（维度 + 失败标签）。
- `benchmarks/finance/anonymization_and_labeling_template.md`：把真实用户输入转换成 benchmark case 的匿名化与标注模板。
- `benchmarks/finance/survey_template.md`：marketing research / 问卷模板（把真实输入与“满意标准”采集成可直接转 case 的格式）。

## 重要说明（请先读）

- v0 样本里的名字/机构/链接均为**虚构占位**（如 `example.com`），不用于衡量真实线上检索效果。
- 如果你要评测“搜人”能力并且希望有稳定的“预期输出”，建议：
  - 对证据做快照：保存关键摘录 + URL + 时间戳，或
  - 使用固定候选池（candidate pool）进行闭卷评测（更可复现）。

## 如何扩充为真实 benchmark（推荐路径）

1) 先用 `finance_v0.json` 跑通团队的“填表/标注/打分”流程（哪怕先不跑模型）。
2) 用 `anonymization_and_labeling_template.md` 把真实样本逐条替换进来（每条样本都尽量带可追溯证据）。
3) 每次迭代只改动一种东西：输入表单、提示词、排序规则或输出格式；然后对比新旧 run 的评分与失败标签分布。

## v0.1 新增的关键 context（尤其适合 banker）

- 找人：支持更结构化的偏好字段（例如 `target_role_titles`、`seniority`、`bank_tier`、`group`/`group_type`、`sector`、`stage`、`recruiting_context`、`contact_channels`）。
- 写信：支持可选 `email_spec`（language/tone/长度/one-ask/value/hard rules/compliance guardrails），便于把“满意标准”写成可验证的约束。
- 证据：profile/candidate 可带 `evidence_snippets`（id + text + url），用于强制引用与减少幻觉。

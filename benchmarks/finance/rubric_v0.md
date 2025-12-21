# Finance Benchmark Rubric (v0.1)

本 rubric 目标：让“找人 + 写信”的评测从主观感受变成可比较的分数与失败原因分布。

## A) 找人（/api/find-recommendations）

### 必须满足（Fail fast）
- 输出为候选列表，且每个候选包含：`name`、`position`、`field`、`match_score`、`match_reason`、`evidence`、`sources`、`uncertainty`
- 不编造可核验事实：若 `sources` 为空，必须 `uncertainty` 标为 high 且不做具体断言

### 评分维度（0-2）

1) 相关性 Relevance
- 2：大多数候选明显符合 `search_intent`/must-have，且避开 must-not
- 1：一半左右符合；有明显跑偏但仍可用
- 0：多数不相关或违背硬约束

2) 证据质量 Evidence
- 2：每个候选至少 1 条可追溯证据（URL + grounded snippet/事实点），且证据与主张一致
- 1：有证据但模糊/不完整（仅 URL 或仅泛泛描述）
- 0：基本无证据或证据与主张不一致

3) 不确定性诚实度 Uncertainty Honesty
- 2：缺证据时明确写不确定，且不扩写细节
- 1：偶尔过度推断
- 0：明显编造（职位/机构/经历）或强断言无证据

4) 可联系性与可用性 Contactability
- 2：候选可联系性强（或与 `contactability` 偏好一致），信息可用于写第一封邮件
- 1：部分可用但信息不足
- 0：候选难以联系或信息过少

### 失败标签（可多选）
- `wrong_target_type`：人群类型错误（岗位/机构/层级）
- `weak_evidence`：证据弱或不可追溯
- `hallucination_person`：编造人物/职位/机构
- `format_missing_fields`：缺字段
- `ignores_constraints`：忽略 must-not / location / seniority 等硬约束

## B) 写信（/api/generate-email）

长度建议：英文按 `max_words`，中文按 `max_chars`（或至少用 case 的 assertions 里声明的单位）。

### 必须满足（Fail fast）
- 必须有 Subject 行（或等价的主题）
- 禁止虚构关系/经历/交易/共同认识
- 不触碰合规禁区（可按 case 的 `assertions.compliance`）

### 评分维度（0-2）

1) 结构完整 Structure
- 2：Subject → why them（基于 receiver evidence）→ value → 单一清晰 ask（含时长/轻量替代）→ opt-out
- 1：结构大体存在但缺一两项
- 0：结构混乱或缺关键请求

2) 事实忠实 Faithfulness
- 2：只引用输入里的事实点；未知处保持保守
- 1：有轻微推断但不伤害真实性
- 0：明显编造或夸大

3) 个性化质量 Personalization
- 2：至少 1-2 个“证据点”驱动的个性化（不是泛夸）
- 1：有个性化但较浅
- 0：通用模板化

4) 清晰度与可执行 Clarity
- 2：ask 非常具体（时长/时间窗口/替代选项），读完可直接回复
- 1：ask 还行但略模糊
- 0：没有明确 ask

5) 金融合规与语气 Compliance & Tone
- 2：专业克制，无投资建议/收益承诺/内幕暗示
- 1：基本 OK，略有边界表达
- 0：明显合规风险

### 失败标签（可多选）
- `missing_subject`
- `ask_unclear`
- `hallucination_relationship`
- `hallucination_credential`
- `mentions_specific_deal_without_source`
- `too_long`
- `compliance_risk`

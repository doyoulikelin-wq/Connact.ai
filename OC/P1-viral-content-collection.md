# P1 — 爆款收集（Viral Content Collection）

> **目标**：利用 OpenClaw 的 Browser Control + Cron + Persistent Memory，建立一套**全自动**、**多平台**、**可学习**的爆款内容采集系统，为后续内容筛选（P2）和脚本改编（P3）提供高质量素材池。

---

## 1. 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                    OpenClaw 本地运行                      │
│                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐   │
│  │ Cron Job │───▶│ Collector│───▶│ Dedup + Score    │   │
│  │ (定时触发)│    │  Skills  │    │ (去重 + 评分排序) │   │
│  └──────────┘    └──────────┘    └──────┬───────────┘   │
│                                         │               │
│                        ┌────────────────┼────────┐      │
│                        ▼                ▼        ▼      │
│                  ┌──────────┐   ┌────────┐  ┌────────┐  │
│                  │ 本地素材库│   │ 日报推送│  │ 周报汇总│ │
│                  │ /data/oc │   │ (Chat) │  │ (Chat) │  │
│                  └──────────┘   └────────┘  └────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 2. 采集平台与优先级

| 优先级 | 平台 | 采集方式 | 频率 | 备注 |
|--------|------|----------|------|------|
| 🔴 P0 | **小红书** | Browser-based 搜索+热门 | 每 5h | 图文+视频并重，与品牌调性最相关 |
| 🔴 P0 | **抖音** | Browser-based 热门榜 + 搜索 | 每 5h | 短视频爆款最多，需抓播放/点赞/评论 |
| 🟡 P1 | **B站** | API + Browser 热门/排行 | 每 10h | 中长视频参考，知识类内容多 |
| 🟡 P1 | **YouTube** | YouTube Data API v3 | 每 10h | 海外对标、先进玩法参考 |
| 🟢 P2 | **Instagram Reels** | Browser-based | 每日 | 视觉风格参考 |
| 🟢 P2 | **Twitter/X** | API 或 Browser | 每日 | 话题热度 + 海外趋势 |
| 🟢 P2 | **微信公众号** | RSS/第三方聚合 | 每日 | 深度文章参考 |

## 3. 采集维度与数据结构

每条爆款内容采集后，存储为以下 JSON 结构：

```json
{
  "id": "uuid-v4",
  "platform": "douyin",
  "collected_at": "2025-01-20T14:00:00Z",
  "content_type": "short_video",
  
  "source": {
    "url": "https://...",
    "creator_name": "某某某",
    "creator_id": "xxx",
    "creator_followers": 1200000,
    "creator_verified": true,
    "creator_category": "财经/职场"
  },
  
  "metrics": {
    "views": 5800000,
    "likes": 230000,
    "comments": 12000,
    "shares": 45000,
    "favorites": 89000,
    "engagement_rate": 0.065,
    "collected_hours_after_publish": 48
  },
  
  "content": {
    "title": "...",
    "description": "...",
    "tags": ["求职", "冷邮件", "networking"],
    "duration_seconds": 45,
    "thumbnail_url": "https://...",
    "transcript_summary": "（OpenClaw 抓取后用 LLM 生成）"
  },
  
  "analysis": {
    "viral_score": 92,
    "hook_type": "反差开头",
    "content_formula": "痛点提问 → 反常识答案 → 行动建议",
    "emotional_trigger": "焦虑+希望",
    "relevance_to_brand": 0.85,
    "replicability": "high",
    "notes": "开头3秒完播率估计极高，使用了「你知道吗」句式"
  },
  
  "status": "new"
}
```

### 字段说明

| 字段组 | 用途 |
|--------|------|
| `source` | 追溯来源，避免侵权 |
| `metrics` | 量化爆款程度，用于排序与筛选 |
| `content` | 内容摘要，供 P2 筛选会快速浏览 |
| `analysis` | **核心价值** — LLM 自动分析爆款套路 |
| `status` | 生命周期管理：`new → reviewed → selected → adapted → discarded` |

## 4. 爆款判定标准（Viral Threshold）

### 4.1 硬指标（自动打分）

| 平台 | 指标 | 爆款阈值 | 权重 |
|------|------|----------|------|
| 抖音 | 点赞数 | ≥ 10万 | 0.3 |
| 抖音 | 评论数 | ≥ 5000 | 0.2 |
| 抖音 | 转发数 | ≥ 1万 | 0.2 |
| 抖音 | 互动率 | ≥ 5% | 0.3 |
| 小红书 | 点赞+收藏 | ≥ 5万 | 0.3 |
| 小红书 | 评论数 | ≥ 2000 | 0.2 |
| 小红书 | 互动率 | ≥ 8% | 0.3 |
| 小红书 | 收藏/赞比 | ≥ 0.3 | 0.2 |
| B站 | 播放量 | ≥ 50万 | 0.3 |
| B站 | 三连率 | ≥ 3% | 0.3 |
| YouTube | Views | ≥ 100K | 0.3 |
| YouTube | 发布天数内达标 | ≤ 7天 | 0.3 |

### 4.2 软指标（LLM 分析补充）

- **Hook 强度**：开头 3 秒是否有反差/悬念/痛点直击
- **内容公式**：是否有可复用的叙事结构
- **情绪触发**：焦虑/好奇/希望/愤怒/共鸣
- **可复制性**：我们团队是否能用类似方式产出
- **品牌相关度**：与 Connact.ai / cold email / networking / 求职 的关联度

### 4.3 综合评分公式

```
viral_score = (
    normalized_hard_score × 0.5 +
    llm_soft_score × 0.3 +
    brand_relevance × 0.2
) × 100
```

- `viral_score ≥ 80`：**A 级爆款**，优先进入 P2 筛选池
- `viral_score 60-79`：**B 级参考**，供周会讨论
- `viral_score < 60`：**C 级归档**，仅存储不推送

## 5. OpenClaw Skill 设计

### 5.1 Skill: `viral-collector`

```yaml
# skills/viral-collector/skill.yaml
name: viral-collector
description: 多平台爆款内容自动采集
triggers:
  - cron: "0 */6 * * *"        # 每 6 小时执行一次
  - command: "collect viral"    # 手动触发
  
config:
  platforms:
    - douyin
    - xiaohongshu
    - bilibili
    - youtube
  keywords:
    - "cold email"
    - "冷邮件"
    - "networking"
    - "求职"
    - "人脉"
    - "职场社交"
    - "留学申请"
    - "career"
    - "outreach"
  max_items_per_run: 50
  storage_path: "./data/oc/viral_pool"
```

### 5.2 Skill: `viral-analyzer`

```yaml
# skills/viral-analyzer/skill.yaml
name: viral-analyzer
description: 对采集到的原始内容进行 LLM 深度分析
triggers:
  - after: viral-collector     # 采集完成后自动触发
  - command: "analyze viral"
  
config:
  model: claude-sonnet          # 分析用模型
  analysis_dimensions:
    - hook_type
    - content_formula
    - emotional_trigger
    - replicability
    - brand_relevance
  batch_size: 20
```

### 5.3 Skill: `viral-reporter`

```yaml
# skills/viral-reporter/skill.yaml
name: viral-reporter
description: 生成并推送爆款日报/周报
triggers:
  - cron: "0 9 * * *"          # 每天早 9 点推送日报
  - cron: "0 9 * * 1"          # 每周一早 9 点推送周报
  - command: "viral report"
  
config:
  daily_top_n: 10               # 日报展示 Top 10
  weekly_top_n: 30              # 周报展示 Top 30
  push_channels:
    - telegram                   # 主推送渠道
    - feishu                     # 飞书群消息（可选）
  report_format: markdown
```

## 6. 执行流程

### 6.1 单次采集流程

```
[Cron 触发 / 手动 "collect viral"]
        │
        ▼
┌─────────────────────┐
│ 1. 加载关键词列表     │
│    + Memory 中的偏好  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 2. 逐平台 Browser   │  ← OpenClaw Browser Control
│    搜索 + 热门页抓取  │     headless Chrome
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 3. 原始数据抽取      │  ← 标题/描述/指标/创作者
│    结构化为 JSON      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 4. 去重（Memory）    │  ← Persistent Memory
│    - URL 去重        │     记住已采集过的内容
│    - 相似标题去重     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 5. 硬指标打分        │  ← 按平台阈值计算
└─────────┬───────────┘
          │
          ▼
┌─────────────────────────┐
│ 6. LLM 软指标分析       │  ← viral-analyzer Skill
│    - Hook 类型          │
│    - 内容公式           │
│    - 品牌相关度         │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────┐
│ 7. 综合评分 + 分级   │  ← A / B / C 级
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 8. 存储到本地素材库   │  → /data/oc/viral_pool/YYYY-MM-DD/
│    + 更新 Memory     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 9. 推送通知          │  ← "发现 8 条 A 级爆款，3 条 B 级"
└─────────────────────┘
```

### 6.2 日报推送模板

```markdown
# 🔥 爆款日报 — 2025-01-20

## A 级爆款（3 条）

### 1. [标题] — 抖音 | @创作者
- 🔗 链接
- 📊 播放 580万 | 点赞 23万 | 评论 1.2万 | 转发 4.5万
- 🎯 Viral Score: 92
- 💡 套路分析: 反差开头 → 痛点直击 → 3步方案 → 行动号召
- 🏷️ 关键词: #求职 #networking #cold email
- ✅ 可复制度: 高

### 2. ...

## B 级参考（5 条）
| # | 标题 | 平台 | Score | 核心套路 |
|---|------|------|-------|---------|
| 1 | ...  | 小红书 | 72  | 清单体  |
| 2 | ...  | B站   | 68  | 故事线  |

## 📈 趋势观察
- 本周"冷邮件"相关内容热度 ↑15%
- 小红书"求职"话题新增爆款明显多于抖音
- Hook 类型趋势: "你知道吗"式提问本周最流行

---
*由 OpenClaw viral-reporter 自动生成*
```

## 7. 文件存储规范

```
data/oc/
├── viral_pool/
│   ├── 2025-01-20/
│   │   ├── raw/                  # 原始采集数据
│   │   │   ├── douyin_001.json
│   │   │   ├── xiaohongshu_001.json
│   │   │   └── ...
│   │   ├── analyzed/             # LLM 分析后的完整数据
│   │   │   ├── douyin_001.json
│   │   │   └── ...
│   │   └── daily_report.md       # 当日日报
│   └── 2025-01-21/
│       └── ...
├── weekly_reports/
│   ├── 2025-W04.md
│   └── ...
├── config/
│   ├── keywords.yaml             # 监控关键词（可动态更新）
│   ├── thresholds.yaml           # 各平台爆款阈值
│   └── preferences.yaml          # 品牌偏好 + 历史反馈
└── archive/                      # 已处理/归档的内容
    └── ...
```

## 8. Memory 利用策略

OpenClaw 的 Persistent Memory 是 P1 最关键的差异化能力：

### 8.1 记住什么

| Memory Key | 内容 | 更新频率 |
|------------|------|----------|
| `viral_urls_seen` | 已采集过的 URL 集合 | 每次采集后 |
| `viral_patterns` | 高分爆款的共性模式 | 每周分析 |
| `keyword_performance` | 每个关键词带来的爆款数量 | 每周统计 |
| `platform_trends` | 各平台近期趋势变化 | 每周更新 |
| `team_preferences` | 团队在 P2 筛选中的偏好反馈 | 每次周会后 |
| `discarded_reasons` | 被丢弃内容的原因标签 | 持续积累 |

### 8.2 利用 Memory 自进化

```
采集 → 分析 → 推送 → 团队反馈（P2 筛选结果）
                              │
                              ▼
                     Memory 更新偏好
                              │
                              ▼
                    下次采集自动调整
                    - 提高/降低某些关键词权重
                    - 调整某平台的阈值
                    - 优化品牌相关度评估
```

## 9. 实施计划

### Phase 1 — MVP（第 1-2 周）

| 任务 | 产出 | 负责 |
|------|------|------|
| 安装配置 OpenClaw | 本地可运行 | 开发 |
| 编写 `viral-collector` Skill（抖音+小红书） | 能采集 2 个平台 | 开发 |
| 确定初始关键词列表 | `keywords.yaml` | 运营 + 开发 |
| 设定爆款阈值 V1 | `thresholds.yaml` | 运营 |
| 手动触发采集并验证数据质量 | 100+ 条样本数据 | 联合验证 |

### Phase 2 — 自动化（第 3-4 周）

| 任务 | 产出 | 负责 |
|------|------|------|
| 编写 `viral-analyzer` Skill | LLM 自动评分 | 开发 |
| 编写 `viral-reporter` Skill | 日报/周报自动推送 | 开发 |
| 配置 Cron 定时任务 | 全自动采集+推送 | 开发 |
| 接入 Telegram/飞书推送 | 团队可接收通知 | 开发 |
| 扩展到 B站 + YouTube | 4 平台覆盖 | 开发 |

### Phase 3 — 学习闭环（第 5-6 周）

| 任务 | 产出 | 负责 |
|------|------|------|
| P2 筛选结果回流 Memory | 偏好自动学习 | 开发 |
| 关键词效果分析 | 自动调整关键词权重 | 开发 + 运营 |
| 爆款模式总结报告 | 月度套路手册 | 运营 |
| 阈值动态调整 | 精准度提升 | 开发 |

## 10. 监控与度量

### 日维度

| 指标 | 目标 |
|------|------|
| 采集总条数 | ≥ 50 条/天 |
| A 级爆款条数 | ≥ 3 条/天 |
| 采集成功率 | ≥ 95%（无报错） |
| 推送及时性 | 早 9 点前完成日报 |

### 周维度

| 指标 | 目标 |
|------|------|
| A 级进入 P2 比例 | ≥ 70% 被团队采纳 |
| 关键词命中率 | 持续提升 |
| 平台覆盖率 | Phase 2 后 ≥ 4 平台 |
| Memory 偏好更新次数 | ≥ 1 次/周 |

### 月维度

| 指标 | 目标 |
|------|------|
| 爆款素材库总量 | ≥ 500 条/月 |
| A 级最终转化为脚本（到 P3）| ≥ 10 条/月 |
| 模式识别准确率 | 人工校验 ≥ 80% |

## 11. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 |
|------|------|------|----------|
| 平台反爬/封号 | 中 | 高 | 控制抓取频率（≤ 50次/h）；使用 Browser 模拟真人行为；准备多账号轮换 |
| 数据质量差（噪音多） | 中 | 中 | 提高硬指标阈值；LLM 二次过滤；团队反馈闭环 |
| LLM 分析成本高 | 低 | 中 | 只对通过硬指标的内容做 LLM 分析；使用 Sonnet 而非 Opus 降本 |
| OpenClaw 版本升级不兼容 | 低 | 中 | 锁定版本；Skill 独立文件，易迁移 |
| 关键词偏移（行业热词变化） | 中 | 低 | Memory 记录热词趋势；月度关键词 review |

## 12. 与后续阶段的接口

P1 的输出是 P2（内容筛选）的输入：

```
P1 输出                          P2 输入
─────────                        ─────────
/data/oc/viral_pool/             周会筛选池
  └── analyzed/*.json     ──▶    - 按 viral_score 排序
                                 - 按 content_formula 分组
daily_report.md           ──▶    团队提前浏览
weekly_reports/           ──▶    周会讨论材料

P2 输出（反馈）                   回流 P1
─────────────                    ────────
selected / discarded      ──▶    Memory 更新偏好
discard_reason            ──▶    优化采集策略 + 阈值
```

---

## 附录 A：初始关键词列表（V1）

### 核心关键词（Brand-direct）
- cold email / 冷邮件
- networking / 人脉 / 社交
- outreach / 主动联系
- connact / 联系人

### 场景关键词（Use-case）
- 求职 / 找工作 / 投简历
- 留学申请 / 套磁 / 联系教授
- 商务拓展 / BD / 合作邀约
- 自我介绍 / elevator pitch

### 方法论关键词（How-to）
- 邮件模板 / email template
- 如何/怎么写邮件
- 回复率 / response rate
- LinkedIn 消息 / 私信技巧

### 情绪/痛点关键词（Emotional）
- 被拒 / 已读不回 / 没回复
- 社恐 / 不敢联系
- 内推 / 找人帮忙

## 附录 B：各平台采集入口（Technical Notes）

| 平台 | 入口页 | 抓取策略 |
|------|--------|----------|
| 抖音 | 搜索页 + 热门榜 | Browser → 搜索关键词 → 滚动加载 → 提取卡片数据 |
| 小红书 | 搜索页 + 发现页 | Browser → 搜索 → 点击笔记 → 提取详情 |
| B站 | 搜索 + 热门排行 | API (`api.bilibili.com`) + Browser 补充 |
| YouTube | YouTube Data API v3 | `search.list` + `videos.list` (quota 注意) |
| Instagram | Reels 搜索 | Browser-based（需登录态） |
| Twitter/X | 搜索 API / Browser | 优先 API，fallback Browser |

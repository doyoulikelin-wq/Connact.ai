# P1 爆款收集 — 模型选择与路由方案（省钱版）

> **核心原则**：P1 工作流中 **80% 的任务不需要 LLM**（纯自动化抓取/计算），剩余 20% 的 LLM 调用也以"轻量层优先 → 按需升级"为原则。**目标月成本 < ¥30（~$4）**。

---

## 1. P1 任务 × 模型需求映射

先明确一点：P1 的九个子步骤中，大部分是纯自动化（Browser + 本地计算），只有分析/生成步骤才需要 LLM。

| 步骤 | 任务 | 是否需要 LLM | 模型层级 | 说明 |
|------|------|:---:|----------|------|
| ① 关键词加载 | 读 YAML + Memory | ❌ | — | 纯文件操作 |
| ② 平台抓取 | Browser Control 爬取 | ❌ | — | OpenClaw headless Chrome，零 LLM 成本 |
| ③ 数据抽取 | HTML → JSON 结构化 | ❌ | — | 正则/CSS选择器/XPath，无需 LLM |
| ④ 去重 | URL + 相似度比对 | ❌ | — | Memory 哈希查重，本地文本相似度 |
| ⑤ 硬指标打分 | 数值阈值比较 | ❌ | — | 纯数学计算，Python 脚本 |
| ⑥ 软指标分析 | Hook/公式/情绪/品牌 | ✅ | **轻量→中等** | **主要 LLM 成本来源** |
| ⑦ 综合评分 | 加权计算 | ❌ | — | 纯公式 |
| ⑧ 存储+Memory | 写文件 + 更新 Memory | ❌ | — | 纯 I/O |
| ⑨ 日报/周报生成 | 模板填充 + 趋势总结 | ✅ | **轻量** | 大部分是模板文本填充 |

**结论**：只有步骤 ⑥ 和 ⑨ 消耗 LLM tokens，合计不超过总工作量的 15%。

---

## 2. 三层模型架构（对齐研究报告）

参照《OpenClaw 可接入模型与定价研究报告》的分层策略，为 P1 定制三层：

### 2.1 模型清单与单价

| 层级 | 模型 | 输入价 ($/MTok) | 输出价 ($/MTok) | 上下文窗口 | P1 用途 |
|------|------|:-:|:-:|:-:|------|
| **轻量** | Z.AI GLM-4.7-FlashX | **$0.07** | **$0.40** | 200K | ⑥ 简单分类（Hook类型、情绪标签） |
| **轻量** | OpenAI gpt-5-nano | $0.05 | $0.40 | 128K | ⑥ 分类任务的备选 |
| **轻量** | Z.AI GLM-4.7-Flash | **免费** | **免费** | 128K | ⑨ 日报模板填充 |
| **中等** | OpenAI gpt-5-mini | $0.25 | $2.00 | 128K | ⑥ 深度内容公式分析 |
| **中等** | MiniMax M2.5 | $0.30 | $1.20 | 200K | ⑥ 中文爆款分析（中文强） |
| **高级** | Anthropic Sonnet 4.6 | $3.00 | $15.00 | 200K | 仅用于月度模式总结（极低频） |

### 2.2 为什么不用高级层做日常分析？

| 对比 | GLM-4.7-FlashX (轻量) | gpt-5-mini (中等) | Opus 4.6 (高级) |
|------|:-:|:-:|:-:|
| 分析一条爆款内容 | ¥0.003 | ¥0.02 | ¥0.25 |
| 1500条/月 | **¥4.5** | ¥30 | ¥375 |
| 能力够用？ | 分类/标签 ✅ | 深度分析 ✅ | 杀鸡用牛刀 ❌ |

**结论**：日常用轻量层，需要深度分析时升级到中等层，高级层仅月度复盘用。

---

## 3. 分步路由策略（静态 + 动态）

### 3.1 步骤 ⑥ 软指标分析 — 两阶段路由

**核心思路**：先用轻量层做快速分类，只对"有潜力"的内容升级到中等层做深度分析。

```
                      通过硬指标(步骤⑤)的内容
                              │
                              ▼
                    ┌──────────────────┐
                    │ 第一阶段：快速分类 │  ← 轻量层 (GLM-4.7-FlashX)
                    │  - Hook 类型标签  │     ~200 tokens/条
                    │  - 情绪标签       │     成本: ¥0.003/条
                    │  - 品牌相关度 0-1 │
                    └────────┬─────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
            brand_relevance      brand_relevance
               ≥ 0.5                < 0.5
                    │                 │
                    ▼                 ▼
          ┌──────────────┐    ┌──────────────┐
          │ 第二阶段：    │    │ 仅保留标签   │
          │ 深度分析      │    │ 跳过深度分析  │
          │ (中等层)      │    │ (省钱)       │
          │ gpt-5-mini    │    └──────────────┘
          │ ~800 tok/条   │
          │ ¥0.02/条     │
          └──────────────┘
```

**预计流量分布**（基于经验估算）：
- 每天采集 50 条 → 通过硬指标约 30 条
- 第一阶段全量：30 条 × ¥0.003 = ¥0.09/天
- 第二阶段（约 40% 进入）：12 条 × ¥0.02 = ¥0.24/天
- **⑥ 日成本 ≈ ¥0.33/天 ≈ ¥10/月**

### 3.2 步骤 ⑨ 日报/周报生成 — 模板优先

日报 90% 是结构化数据填充模板，只有"趋势观察"部分需要 LLM 生成。

| 日报组成 | 方式 | LLM? |
|----------|------|:---:|
| A 级爆款列表 | 从 JSON 直接渲染 Markdown | ❌ |
| B 级参考表格 | 从 JSON 直接渲染 | ❌ |
| 数据统计行 | Python 聚合计算 | ❌ |
| 📈 趋势观察（3-5 句） | LLM 总结 | ✅ |

```
趋势观察 prompt:
  - 输入: 本周 vs 上周的关键词热度变化 JSON + 平台分布 JSON (~300 tokens)
  - 输出: 3-5 句趋势判断 (~150 tokens)
  - 模型: Z.AI GLM-4.7-Flash（免费档）或 GLM-4.7-FlashX
```

**⑨ 日成本 ≈ ¥0（用免费 Flash）~ ¥0.01/天（用 FlashX）**

### 3.3 月度模式复盘 — 中等/高级层

每月一次，对本月所有 A 级爆款做深度模式总结：

```
输入: 月度 A 级爆款集合的 analysis JSON（~50 条 × ~200 tokens = 10K tokens）
输出: 结构化月度套路报告（~2K tokens）
模型: gpt-5-mini（中等层）或 Sonnet 4.6（如需最高质量）
```

| 模型 | 单次成本 |
|------|----------|
| gpt-5-mini | ¥0.06 |
| Sonnet 4.6 | ¥0.75 |

**月度复盘成本 ≈ ¥0.06 ~ ¥0.75（一个月只做一次）**

---

## 4. 月度成本预算（保守估算）

### 4.1 LLM 调用成本

| 项目 | 频率 | 模型 | 月 Token 量 | 月成本 |
|------|------|------|:-:|:-:|
| ⑥ 快速分类 | 30条/天 ×30天 | GLM-4.7-FlashX | 入180K + 出90K | **¥3.0** |
| ⑥ 深度分析 | 12条/天 ×30天 | gpt-5-mini | 入288K + 出180K | **¥7.2** |
| ⑨ 趋势总结 | 1次/天 ×30天 | GLM-4.7-Flash | ~13.5K | **¥0（免费）** |
| 月度复盘 | 1次/月 | gpt-5-mini | ~12K | **¥0.06** |
| **合计** | | | | **≈ ¥10.3/月** |

### 4.2 平台/订阅成本

| 项目 | 方案 | 月成本 |
|------|------|:-:|
| OpenClaw | 自托管（开源免费） | ¥0 |
| Z.AI API (FlashX + Flash) | 按量计费 | 已含上表 |
| OpenAI gpt-5-mini API | 按量计费 | 已含上表 |
| 服务器/本地电脑 | 本地 Mac 运行 | ¥0（已有） |
| **合计** | | **≈ ¥10/月** |

### 4.3 三档预算对比

| 方案 | 模型组合 | 月成本 | 适用场景 |
|------|----------|:-:|------|
| 🟢 **极省版** | 全量用 Z.AI Flash 免费档 + FlashX | **≈ ¥3/月** | 分析精度稍低，但够用（MVP） |
| 🟡 **推荐版** | FlashX 分类 + gpt-5-mini 深度 | **≈ ¥10/月** | 性价比最优，分析质量有保障 |
| 🔴 高配版 | gpt-5-mini 全量 + Sonnet 月度 | **≈ ¥32/月** | 追求最高分析质量 |

> **推荐方案**：🟡 推荐版。月成本 ≈ ¥10，相当于一杯奶茶。

---

## 5. OpenClaw 配置实现

### 5.1 `openclaw.json` — P1 专用模型配置

```json5
{
  env: {
    ZAI_API_KEY: "${ZAI_API_KEY}",              // 智谱 API Key
    OPENAI_API_KEY: "${OPENAI_API_KEY}",        // OpenAI API Key（gpt-5-mini）
    // Anthropic 仅月度复盘可选，平时不需要
    // ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}",
  },

  agents: {
    defaults: {
      // 模型白名单 — 只允许这几个，防止误触高价模型
      models: {
        "zai/glm-4.7-flash":    { alias: "free" },
        "zai/glm-4.7-flashx":   { alias: "lite" },
        "openai/gpt-5-nano":    { alias: "nano" },
        "openai/gpt-5-mini":    { alias: "medium" },
      },

      // 默认主模型 = 轻量层（成本最低）
      model: {
        primary: "zai/glm-4.7-flashx",
        fallbacks: [
          "openai/gpt-5-nano",     // 轻量备选
          "openai/gpt-5-mini",     // 最终兜底
        ],
      },

      // 不需要 imageModel（P1 不处理图片输入）
    },
  },
}
```

### 5.2 路由策略配置 `router.yaml`

```yaml
# OC/config/router.yaml — P1 爆款收集专用

catalog:
  lite:
    - id: "zai/glm-4.7-flash"
      price_per_mtok:
        input: 0.00      # 免费
        output: 0.00     # 免费
      context_window: 128000
      modalities: ["text"]
      note: "免费档，用于日报模板/简单文本"

    - id: "zai/glm-4.7-flashx"
      price_per_mtok:
        input: 0.07
        output: 0.40
      context_window: 200000
      modalities: ["text"]
      note: "P1 第一阶段分类的主力"

    - id: "openai/gpt-5-nano"
      price_per_mtok:
        input: 0.05
        output: 0.40
      context_window: 128000
      modalities: ["text"]
      note: "轻量备选"

  medium:
    - id: "openai/gpt-5-mini"
      price_per_mtok:
        input: 0.25
        output: 2.00
      context_window: 128000
      modalities: ["text"]
      note: "P1 第二阶段深度分析"

    - id: "minimax/MiniMax-M2.5"
      price_per_mtok:
        input: 0.30
        output: 1.20
      context_window: 200000
      modalities: ["text"]
      note: "中文表现好，200K 上下文"

  premium:
    - id: "anthropic/claude-sonnet-4-6"
      price_per_mtok:
        input: 3.00
        output: 15.00
      context_window: 200000
      modalities: ["text", "image"]
      note: "仅月度复盘可选，P1 日常不用"

# ── P1 专用路由规则 ──
policy:
  static_rules:
    # 规则 1：快速分类任务 → 轻量层
    - name: "p1_quick_classify"
      when:
        task_type: "classify"
        keywords_any: ["hook_type", "emotion_tag", "brand_score", "分类", "标签"]
      route_to: "lite"
      prefer: "zai/glm-4.7-flashx"

    # 规则 2：日报/周报生成 → 免费档
    - name: "p1_report_gen"
      when:
        task_type: "report"
        keywords_any: ["日报", "周报", "趋势", "report", "summary"]
      route_to: "lite"
      prefer: "zai/glm-4.7-flash"   # 免费！

    # 规则 3：深度内容分析 → 中等层
    - name: "p1_deep_analysis"
      when:
        task_type: "analyze"
        keywords_any: ["content_formula", "公式", "叙事结构", "深度分析", "replicability"]
      route_to: "medium"
      prefer: "openai/gpt-5-mini"

    # 规则 4：月度复盘 → 中等层（可选升级到高级）
    - name: "p1_monthly_review"
      when:
        task_type: "review"
        keywords_any: ["月度", "monthly", "模式总结", "pattern"]
      route_to: "medium"
      prefer: "openai/gpt-5-mini"

  dynamic:
    # 延迟熔断（参考研究报告阈值）
    latency_p95_ms_threshold:
      lite: 8000          # 轻量层 8s 熔断
      medium: 12000       # 中等层 12s 熔断
    error_rate_threshold: 0.05
    circuit_break_seconds: 600

    # P1 每日预算上限（触发降级）
    budget_daily_usd:
      target: 0.5          # ¥3.5/天
      hard_limit: 1.0      # ¥7/天（绝不超过）

    # 降级规则
    degradation:
      - when: "daily_budget_remaining < 15%"
        action: "medium → lite"
      - when: "daily_budget_remaining < 5%"
        action: "lite → free (glm-4.7-flash only)"
      - when: "daily_budget_remaining = 0"
        action: "skip LLM analysis, only keep hard metrics"
```

### 5.3 Prompt 模板（成本优化版）

#### 第一阶段：快速分类 Prompt（轻量层）

```
目标: 用最少 token 完成分类，严格控制输出格式。

System: 你是内容分类器。只输出 JSON，不要解释。

User:
对以下内容做分类：
标题: {title}
描述: {description} (截取前200字)
平台: {platform}
指标: 点赞{likes} 评论{comments} 转发{shares}

输出格式（严格 JSON，无其他文字）：
{"hook":"反差|悬念|痛点|数据|故事|清单|无","emotion":"焦虑|好奇|希望|愤怒|共鸣|无","brand_rel":0.0-1.0,"worth_deep":true/false}
```

**Token 估算**：输入 ~180 tokens，输出 ~30 tokens → ¥0.003/条 (FlashX)

#### 第二阶段：深度分析 Prompt（中等层）

```
System: 你是短视频爆款分析师。基于证据分析，不要编造。

User:
## 内容信息
- 标题: {title}
- 描述: {description}
- 平台: {platform}
- 创作者: {creator_name} (粉丝{followers})
- 标签: {tags}
- 时长: {duration}s
- 指标: 播放{views} 点赞{likes} 评论{comments} 转发{shares} 收藏{favorites}
- 互动率: {engagement_rate}

## 已知标签
- Hook类型: {hook_type_from_stage1}
- 情绪: {emotion_from_stage1}
- 品牌相关度: {brand_rel_from_stage1}

## 请分析
1. content_formula: 用"→"连接的叙事结构（如"痛点提问→反常识答案→行动建议"）
2. hook_detail: 开头hook的具体手法（50字内）
3. replicability: high/medium/low + 原因（30字内）
4. adaptation_hint: 如果我们团队（冷邮件/networking工具）要借鉴，建议怎么改编（50字内）

输出纯 JSON。
```

**Token 估算**：输入 ~350 tokens，输出 ~200 tokens → ¥0.02/条 (gpt-5-mini)

#### 日报趋势总结 Prompt（免费层）

```
System: 用3-5句话总结以下数据变化趋势。简洁、有洞察。

User:
本周采集数据:
- 总量: {total}条, A级{a_count}条, B级{b_count}条
- 关键词热度变化: {keyword_delta_json}
- 平台分布: {platform_dist_json}
- 本周最流行Hook类型: {top_hooks}
- 上周对比: A级{delta_a}%, 总量{delta_total}%

输出3-5句趋势观察。
```

**Token 估算**：输入 ~200 tokens，输出 ~120 tokens → **¥0（Flash 免费）**

---

## 6. 路由器实现（Python 精简版）

```python
"""
P1 专用模型路由器 — 配合 OpenClaw /hooks/agent 使用
把路由决策与 OpenClaw 执行引擎解耦
"""
import os
import json
import time
import yaml
import requests
from dataclasses import dataclass
from typing import Dict, List, Optional


# ── 数据结构 ──

@dataclass
class Model:
    id: str
    input_price: float   # USD per 1M input tokens
    output_price: float  # USD per 1M output tokens
    context_window: int

@dataclass
class UsageTracker:
    """当日用量追踪"""
    daily_cost_usd: float = 0.0
    daily_requests: int = 0
    date: str = ""

    def add(self, cost: float):
        today = time.strftime("%Y-%m-%d")
        if self.date != today:
            self.daily_cost_usd = 0.0
            self.daily_requests = 0
            self.date = today
        self.daily_cost_usd += cost
        self.daily_requests += 1

    def remaining_pct(self, budget: float) -> float:
        if budget <= 0:
            return 0.0
        return max(0, (budget - self.daily_cost_usd) / budget)


# ── 路由核心 ──

class P1Router:
    def __init__(self, config_path: str = "OC/config/router.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        self.tiers: Dict[str, List[Model]] = {}
        for tier, items in cfg["catalog"].items():
            self.tiers[tier] = [
                Model(
                    id=m["id"],
                    input_price=m["price_per_mtok"]["input"],
                    output_price=m["price_per_mtok"]["output"],
                    context_window=m["context_window"],
                )
                for m in items
            ]

        self.policy = cfg["policy"]
        self.tracker = UsageTracker()
        self.circuit_open: Dict[str, float] = {}

    def estimate_cost(self, model: Model, in_tok: int, out_tok: int) -> float:
        return (in_tok / 1_000_000) * model.input_price + \
               (out_tok / 1_000_000) * model.output_price

    def route(self, task_type: str, est_in_tokens: int = 500,
              est_out_tokens: int = 200) -> Model:
        """
        P1 静态路由 + 动态降级

        task_type: "classify" | "report" | "analyze" | "review"
        """
        # 1. 静态规则匹配
        tier = "lite"  # 默认最便宜
        preferred = None

        for rule in self.policy["static_rules"]:
            if rule["when"].get("task_type") == task_type:
                tier = rule["route_to"]
                preferred = rule.get("prefer")
                break

        # 2. 动态降级检查
        budget = self.policy["dynamic"]["budget_daily_usd"]["target"]
        remaining = self.tracker.remaining_pct(budget)

        if remaining < 0.05:
            # 预算几乎耗尽 → 只用免费模型
            tier = "lite"
            preferred = "zai/glm-4.7-flash"
        elif remaining < 0.15 and tier == "medium":
            # 预算紧张 → 中等降级到轻量
            tier = "lite"

        # 3. 在目标 tier 中选模型
        candidates = self.tiers.get(tier, self.tiers["lite"])

        # 优先选 preferred
        if preferred:
            for m in candidates:
                if m.id == preferred and not self._is_circuit_open(m.id):
                    return m

        # 否则按顺序选第一个可用的
        for m in candidates:
            if not self._is_circuit_open(m.id):
                return m

        # 所有都熔断了 → 用 lite 第一个（最稳的免费档）
        return self.tiers["lite"][0]

    def record_success(self, model: Model, in_tok: int, out_tok: int):
        cost = self.estimate_cost(model, in_tok, out_tok)
        self.tracker.add(cost)

    def record_failure(self, model_id: str):
        break_seconds = self.policy["dynamic"]["circuit_break_seconds"]
        self.circuit_open[model_id] = time.time() + break_seconds

    def _is_circuit_open(self, model_id: str) -> bool:
        return time.time() < self.circuit_open.get(model_id, 0)

    def get_daily_summary(self) -> dict:
        return {
            "date": self.tracker.date,
            "cost_usd": round(self.tracker.daily_cost_usd, 4),
            "cost_cny": round(self.tracker.daily_cost_usd * 7.2, 2),
            "requests": self.tracker.daily_requests,
            "budget_remaining_pct": round(
                self.tracker.remaining_pct(
                    self.policy["dynamic"]["budget_daily_usd"]["target"]
                ) * 100, 1
            ),
        }


# ── 调用 OpenClaw ──

def call_openclaw(router: P1Router, task_type: str, message: str,
                  est_in: int = 500, est_out: int = 200) -> dict:
    """通过 /hooks/agent 触发 OpenClaw，模型由路由器决定"""

    model = router.route(task_type, est_in, est_out)

    openclaw_url = os.environ.get("OPENCLAW_BASE_URL", "http://127.0.0.1:18789")
    token = os.environ.get("OPENCLAW_HOOK_TOKEN", "")

    resp = requests.post(
        f"{openclaw_url.rstrip('/')}/hooks/agent",
        headers={
            "x-openclaw-token": token,
            "content-type": "application/json",
        },
        json={
            "name": "P1-viral",
            "message": message,
            "model": model.id,           # 关键：每次 run 指定模型
            "wakeMode": "next-heartbeat",
        },
        timeout=30,
    )

    if resp.ok:
        router.record_success(model, est_in, est_out)
        return {"model": model.id, "result": resp.json()}
    else:
        router.record_failure(model.id)
        raise RuntimeError(f"OpenClaw call failed: {resp.status_code}")


# ── 使用示例 ──

if __name__ == "__main__":
    router = P1Router()

    # 示例 1: 快速分类（轻量层）
    result = call_openclaw(
        router, "classify",
        '{"title":"3步搞定冷邮件","platform":"douyin","likes":150000}',
        est_in=180, est_out=30,
    )
    print(f"分类用了: {result['model']}")

    # 示例 2: 深度分析（中等层）
    result = call_openclaw(
        router, "analyze",
        '完整内容分析 prompt...',
        est_in=350, est_out=200,
    )
    print(f"分析用了: {result['model']}")

    # 示例 3: 日报趋势（免费层）
    result = call_openclaw(
        router, "report",
        '本周数据 JSON...',
        est_in=200, est_out=120,
    )
    print(f"日报用了: {result['model']}")

    # 查看当日成本
    print(router.get_daily_summary())
```

---

## 7. 与 P1 Skill 集成方式

### viral-analyzer Skill 改造

原版 Skill 配置了固定 `model: claude-sonnet`（贵），改为由路由器控制：

```yaml
# skills/viral-analyzer/skill.yaml（优化版）
name: viral-analyzer
description: 对采集到的原始内容进行分层 LLM 分析
triggers:
  - after: viral-collector
  - command: "analyze viral"

config:
  # 不再固定 model，由路由器决定
  # model: claude-sonnet  ← 删除这行！

  analysis_stages:
    # 第一阶段：全量快速分类
    - name: quick_classify
      task_type: classify          # 路由器用这个字段选模型
      filter: "hard_score > 0"     # 通过硬指标的都做
      output_fields:
        - hook_type
        - emotion_tag
        - brand_relevance
        - worth_deep_analysis

    # 第二阶段：条件性深度分析
    - name: deep_analysis
      task_type: analyze
      filter: "worth_deep_analysis == true AND brand_relevance >= 0.5"
      output_fields:
        - content_formula
        - hook_detail
        - replicability
        - adaptation_hint

  batch_size: 20
  # 路由器配置路径
  router_config: "./OC/config/router.yaml"
```

### viral-reporter Skill 改造

```yaml
# skills/viral-reporter/skill.yaml（优化版）
name: viral-reporter
description: 生成并推送爆款日报/周报
triggers:
  - cron: "0 9 * * *"
  - cron: "0 9 * * 1"
  - command: "viral report"

config:
  daily_top_n: 10
  weekly_top_n: 30

  # 报告生成策略
  report_strategy:
    data_section: "template"          # 数据部分用模板渲染，零 LLM 成本
    trend_section:
      task_type: report               # 路由到免费 Flash 模型
      max_sentences: 5

    # 附加：当日路由器成本摘要
    include_cost_summary: true        # 每日报告里附上模型成本

  push_channels:
    - telegram
    - feishu
  report_format: markdown
```

---

## 8. 成本监控与告警

### 8.1 在日报中附加成本信息

```markdown
## 💰 今日 AI 成本
- 模型调用: 42 次
- 总成本: ¥0.33 ($0.046)
- 预算使用: 13.2%
- 模型分布: FlashX×30, gpt-5-mini×12
- 本月累计: ¥8.7 ($1.21)
```

### 8.2 告警规则

| 触发条件 | 动作 |
|----------|------|
| 日成本 > ¥2 (40% 日预算) | Telegram 通知：成本偏高 |
| 日成本 > ¥3.5 (target) | 自动降级：medium → lite |
| 日成本 > ¥7 (hard_limit) | 自动停止 LLM 调用，只保留硬指标 |
| 某模型连续 3 次超时 | 熔断 10min，切换备选 |
| 某模型错误率 > 5% | 熔断 10min + Telegram 通知 |

### 8.3 月度成本仪表盘

```
┌─────────────────────────────────────────────┐
│         P1 月度 AI 成本报告 — 2026-03        │
├─────────────────────────────────────────────┤
│ 总成本:  ¥10.3 / ¥30 预算  ✅ 健康          │
│ ─────────────[====>                ] 34%    │
│                                             │
│ 模型分布:                                    │
│   GLM-4.7-Flash  (免费)  : 30 次   ¥0.0    │
│   GLM-4.7-FlashX (轻量)  : 900 次  ¥3.0    │
│   gpt-5-mini     (中等)  : 360 次  ¥7.2    │
│   Sonnet 4.6     (高级)  : 1 次    ¥0.06   │
│                                             │
│ 日均: ¥0.34 | 峰值: ¥0.82 (03-15)          │
│ 降级触发: 2 次 | 熔断触发: 0 次              │
└─────────────────────────────────────────────┘
```

---

## 9. 进阶省钱技巧

### 9.1 Prompt Caching（Anthropic / OpenAI）

如果后续升级到中等/高级层的使用频率增加，利用 Prompt Caching：

- **System prompt 缓存**：分类和分析的 system prompt 是固定的，缓存后无需重复计费
- Anthropic 默认 5 分钟缓存 TTL，可选更长
- OpenAI 也有 cached input 折扣（约 50%）

**潜在节省**：中等层成本可再降 30-50%

### 9.2 Batch API（OpenAI）

对于非实时的深度分析（可以等几小时出结果）：

```python
# 将一天的深度分析任务攒成一批，用 Batch API 提交
# Batch API 提供 ~50% 折扣
batch_items = collect_items_needing_deep_analysis()
if len(batch_items) >= 10:
    submit_openai_batch(batch_items)  # 成本直接减半
```

**潜在节省**：深度分析成本从 ¥7.2 → ¥3.6/月

### 9.3 本地小模型兜底

如果未来采集量增长到 200+条/天，可考虑本地部署小模型做第一阶段分类：

| 方案 | 模型 | 硬件要求 | 成本 |
|------|------|----------|------|
| Ollama + Qwen2.5-7B | 本地推理 | 16GB RAM Mac | ¥0（电费忽略） |
| llama.cpp + Phi-3 | 本地推理 | 8GB RAM | ¥0 |

但在当前 50条/天 的量级，API 调用成本已经很低（¥3/月），本地部署的运维成本反而更高，**暂不推荐**。

### 9.4 阿里云百炼 Coding Plan 作为替代方案

如果不想管理多个 API Key：

| Plan | 月费 | 配额 | 适合 P1？ |
|------|------|------|:-:|
| Lite | ¥40/月（首月¥7.9） | 1200 req/5h, 18000/月 | ✅ 完全够用 |
| Pro | ¥200/月 | 6000 req/5h, 90000/月 | ❌ 太贵了 |

但 P1 月请求量只有 ~1300 次，按量计费（FlashX + gpt-5-mini）只需 ¥10/月，**比百炼 Lite 的 ¥40 便宜 4 倍**。所以**按量计费更划算**。

> 结论：百炼 Coding Plan 更适合"高频 Agent 交互"场景（如 P3 脚本改编、P9 优化迭代），**P1 用按量计费最省**。

---

## 10. 决策总结

```
┌───────────────────────────────────────────────────────────────┐
│                    P1 模型路由决策树                            │
│                                                               │
│  任务进来                                                      │
│    │                                                          │
│    ├─ 采集/去重/硬指标 ──→ 不用 LLM（¥0）                      │
│    │                                                          │
│    ├─ 快速分类 ──→ GLM-4.7-FlashX（¥0.003/条）                 │
│    │    │                                                     │
│    │    ├─ 品牌相关度 < 0.5 ──→ 结束（省钱）                    │
│    │    │                                                     │
│    │    └─ 品牌相关度 ≥ 0.5 ──→ gpt-5-mini 深度分析（¥0.02/条） │
│    │                                                          │
│    ├─ 日报趋势 ──→ GLM-4.7-Flash（免费）                       │
│    │                                                          │
│    └─ 月度复盘 ──→ gpt-5-mini（¥0.06/次）                      │
│                                                               │
│  月总成本: ≈ ¥10                                               │
│  相比全量用 Sonnet: 省 97%                                     │
│  相比全量用 gpt-5-mini: 省 67%                                 │
└───────────────────────────────────────────────────────────────┘
```

---

## 附录：关键参考

- 《OpenClaw 可接入模型与定价研究报告》(2026-02-28) — 模型定价表、分层策略、路由流程图、配置教程
- OpenClaw 官方文档：[Model Providers](https://docs.openclaw.ai/concepts/model-providers)、[Model Failover](https://docs.openclaw.ai/concepts/model-failover)、[Webhooks](https://docs.openclaw.ai/automation/webhook)
- Z.AI 免费模型：[定价页](https://docs.z.ai/guides/overview/pricing) — GLM-4.7-Flash 免费档
- OpenAI Batch API：[文档](https://developers.openai.com/api/docs/pricing/) — 批处理 50% 折扣

# Marketing 数字员工计划 — 基于 OpenClaw

## 全流程概览

```
爆款收集 → 内容筛选（周会） → 脚本改编 → 拍摄制作 → 剪辑优化 → 发布上线 → 数据监测 → 周复盘 → 优化迭代
   P1            P2              P3           P4           P5          P6          P7         P8          P9
  [本文档]      [TODO]          [TODO]       [TODO]       [TODO]      [TODO]      [TODO]     [TODO]      [TODO]
```

## 为什么用 OpenClaw？

| 能力 | 在内容流水线中的作用 |
|------|---------------------|
| **24/7 后台运行** | 全天候爬取/监控多平台爆款内容 |
| **Persistent Memory** | 记住品牌调性、历史爆款模式、筛选偏好 |
| **Browser Control** | 自动打开抖音/小红书/YouTube 等平台抓取 |
| **Skills/Plugins** | 自定义爆款采集、数据分析、报告生成等技能 |
| **Chat Integration** | 通过飞书/微信/Telegram 直接推送爆款日报 |
| **File System Access** | 本地存储、整理素材库、生成结构化文档 |
| **Cron Jobs** | 定时采集、定时推送、定时复盘 |
| **Memory + Context** | 越用越精准——学习你的审美偏好和行业 know-how |

## 文档索引

| 文件 | 内容 |
|------|------|
| [P1-viral-content-collection.md](./P1-viral-content-collection.md) | **P1 爆款收集** — 完整执行计划 |
| [P1-model-routing-plan.md](./P1-model-routing-plan.md) | **P1 模型选择与路由方案（省钱版）** — 三层模型架构 + 成本估算 + 路由器实现 |
| [OpenClaw 可接入模型与定价研究报告.pdf](./OpenClaw%20可接入模型与定价研究报告.pdf) | 模型定价对比 + 分层路由策略设计（参考资料） |
| README.md（本文件） | 全流程概览与架构说明 |

## Quick Start（部署 OpenClaw）

```bash
# 1. 安装 OpenClaw
curl -fsSL https://openclaw.ai/install.sh | bash

# 2. 配置 LLM（推荐 Claude / GPT-4o）
# 在 OpenClaw 配置中设置 API Key

# 3. 加载爆款采集 Skill
# 将 P1 中的 skill 文件放入 OpenClaw skills 目录

# 4. 设置定时任务
# OpenClaw 会按 cron 配置自动执行采集
```

# Honest Connect Email Agent (v1)

命令行小工具：

- **v1 核心**：读取两份 PDF 简历（发送者、接收者），自动抽取结构化信息，再结合目标字符串生成一封真诚的第一封冷邮件（包含 Subject + Body）。
- 同时兼容 v0 的 JSON 输入，便于手动调试或补充更详细的信息。

## 准备工作
1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 设置 OpenAI API Key：
   ```bash
   export OPENAI_API_KEY=your_api_key
   ```

## PDF 输入（推荐）
```bash
python -m src.cli \
  --sender-pdf /path/to/sender.pdf \
  --receiver-pdf /path/to/receiver.pdf \
  --motivation "为什么想联系对方" \
  --ask "希望对方帮什么" \
  --goal "希望邀请对方聊 20 分钟，讨论他最近的项目和你的相关经验"
```

命令会自动：
1. 使用 PyPDF2 提取 PDF 纯文本；
2. 调用 OpenAI 模型将文本整理成结构化 Profile（name/education/experiences/skills/projects/raw_text）；
3. 结合你提供的 motivation 与 ask，生成一封可直接粘贴的邮件。

可选参数：
- `--receiver-context`: 你与收件人的关系或你关注的近况（可选）。
- `--model`: 选择调用的 OpenAI 模型，默认 `gpt-4o-mini`。

## JSON 输入（兼容 v0）
```bash
python -m src.cli \
  --sender-json examples/sender.json \
  --receiver-json examples/receiver.json \
  --goal "希望邀请对方聊 20 分钟，讨论他最近的项目和你的相关经验"
```

示例文件在 `examples/` 目录下，字段除了 `name`、`raw_text`、`motivation`、`ask`，也支持 `education`、`experiences`、`skills`、`projects`（可选）。

命令会将生成的邮件文本输出到终端，可直接复制粘贴到邮箱客户端。

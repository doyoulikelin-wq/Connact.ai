#!/bin/bash
# 本地开发启动脚本 - 包含管理员配置

# 基础配置
export SECRET_KEY="your-secret-key-here"
export INVITE_ONLY="false"  # 本地开发关闭邀请码

# 管理员配置（设置你的邮箱为管理员）
export ADMIN_EMAILS="your-email@example.com"  # 用逗号分隔多个管理员邮箱

# API Keys (可选)
# export GEMINI_API_KEY="your-gemini-key"
# export OPENAI_API_KEY="your-openai-key"
# export APOLLO_API_KEY="your-apollo-key"

# 企业微信错误通知 (可选)
# export WECHAT_WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key"

# 启动应用
echo "🚀 启动 Connact.ai (Admin 模式)"
echo "管理员邮箱: $ADMIN_EMAILS"
echo "访问 http://localhost:5000 查看应用"
echo "管理员登录后会自动跳转到 /admin 页面"
echo ""

python app.py

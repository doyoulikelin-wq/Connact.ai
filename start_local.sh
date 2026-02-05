#!/bin/bash

# Local Development Startup Script
# 本地开发环境启动脚本

echo "🚀 Starting Connact.ai Local Development Server"
echo ""

# 设置端口（5001被占用时使用5002）
export PORT=5002

# API Keys - 请设置你自己的 Keys
export APOLLO_API_KEY="${APOLLO_API_KEY:-your_apollo_key_here}"
export MOONSHOT_API_KEY="${MOONSHOT_API_KEY:-your_moonshot_key_here}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-your_openai_key_here}"

# 可选: GEMINI 和 SERPAPI Keys（如果环境变量已设置则使用，否则使用占位符）
export GEMINI_API_KEY="${GEMINI_API_KEY:-your_gemini_key_here}"
export SERPAPI_KEY="${SERPAPI_KEY:-your_serpapi_key_here}"

# Flask 配置
export SECRET_KEY="connact-dev-secret-2026"
export INVITE_ONLY="true"
export INVITE_CODE="test"

# 数据收集（可选）
export COLLECT_PROMPTS="true"

echo "✅ Environment variables set:"
echo "   PORT: $PORT"
echo "   APOLLO_API_KEY: ${APOLLO_API_KEY:0:10}..."
echo "   MOONSHOT_API_KEY: ${MOONSHOT_API_KEY:0:10}..."
echo "   OPENAI_API_KEY: ${OPENAI_API_KEY:0:15}..."
echo "   GEMINI_API_KEY: ${GEMINI_API_KEY:0:10}..."
echo "   SERPAPI_KEY: ${SERPAPI_KEY:0:10}..."
echo "   INVITE_CODE: $INVITE_CODE"
echo ""
echo "📝 Access the app at: http://localhost:$PORT"
echo "🔑 Login with invite code: $INVITE_CODE"
echo ""
echo "Press Ctrl+C to stop the server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 启动应用
python app.py

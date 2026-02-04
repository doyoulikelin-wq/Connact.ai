#!/bin/bash
# Connact.ai 阿里云一键部署脚本
# 使用方法：在阿里云服务器上执行此脚本

set -e

echo "=========================================="
echo "🚀 Connact.ai 阿里云部署脚本"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为 root 用户
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}❌ 请使用 root 用户运行此脚本${NC}" 
   echo "   sudo su"
   exit 1
fi

# 1. 更新系统
echo -e "${GREEN}📦 步骤 1/10: 更新系统包...${NC}"
apt update && apt upgrade -y

# 2. 安装依赖
echo -e "${GREEN}📦 步骤 2/10: 安装依赖（Python, Nginx, Supervisor）...${NC}"
apt install -y python3.10 python3.10-venv python3-pip nginx supervisor git curl

# 3. 创建应用用户
echo -e "${GREEN}👤 步骤 3/10: 创建应用用户...${NC}"
if ! id "connact" &>/dev/null; then
    useradd -m -s /bin/bash connact
    echo -e "${GREEN}✅ 创建用户 connact${NC}"
else
    echo -e "${YELLOW}⚠️  用户 connact 已存在，跳过${NC}"
fi

# 4. 克隆代码
echo -e "${GREEN}📥 步骤 4/10: 从 GitHub 克隆代码...${NC}"
cd /home/connact
if [ -d "Connact.ai" ]; then
    echo -e "${YELLOW}⚠️  目录已存在，更新代码...${NC}"
    cd Connact.ai
    sudo -u connact git pull origin main
else
    sudo -u connact git clone https://github.com/doyoulikelin-wq/Connact.ai.git
    cd Connact.ai
    echo -e "${GREEN}✅ 代码克隆完成${NC}"
fi

# 5. 创建虚拟环境并安装依赖
echo -e "${GREEN}📦 步骤 5/10: 安装 Python 依赖（可能需要几分钟）...${NC}"
sudo -u connact python3 -m venv venv
sudo -u connact ./venv/bin/pip install --upgrade pip -q
sudo -u connact ./venv/bin/pip install -r requirements.txt -q
sudo -u connact ./venv/bin/pip install gunicorn -q
echo -e "${GREEN}✅ Python 依赖安装完成${NC}"

# 6. 配置环境变量
echo -e "${GREEN}⚙️  步骤 6/10: 配置环境变量...${NC}"
if [ ! -f ".env" ]; then
    SECRET_KEY=$(openssl rand -hex 32)
    cat > .env << EOF
# ==========================================
# Connact.ai 环境变量配置
# ==========================================

# API Keys（必填）
GEMINI_API_KEY=your_gemini_api_key_here
# OPENAI_API_KEY=your_openai_key_here  # 可选

# Flask 配置
SECRET_KEY=${SECRET_KEY}
FLASK_ENV=production

# 邀请码（可选，用于访问控制）
INVITE_CODE=beta2026

# Google OAuth（可选）
# GOOGLE_CLIENT_ID=your_google_client_id
# GOOGLE_CLIENT_SECRET=your_google_client_secret

# 数据存储
DATA_DIR=/home/connact/Connact.ai/data
DB_PATH=/home/connact/Connact.ai/data/app.db

# 日志级别
LOG_LEVEL=INFO
EOF
    chown connact:connact .env
    chmod 600 .env
    echo -e "${GREEN}✅ 环境变量文件已创建${NC}"
    echo -e "${YELLOW}⚠️  重要：请稍后编辑 .env 文件填入真实的 API Key${NC}"
else
    echo -e "${YELLOW}⚠️  .env 文件已存在，跳过创建${NC}"
fi

# 7. 创建数据目录
echo -e "${GREEN}📁 步骤 7/10: 创建数据目录...${NC}"
mkdir -p /home/connact/Connact.ai/data
mkdir -p /home/connact/Connact.ai/data/users
mkdir -p /home/connact/Connact.ai/data/prompt_logs
chown -R connact:connact /home/connact/Connact.ai/data
chmod -R 755 /home/connact/Connact.ai/data

# 8. 配置 Supervisor
echo -e "${GREEN}⚙️  步骤 8/10: 配置 Supervisor（进程守护）...${NC}"
cat > /etc/supervisor/conf.d/connact.conf << 'EOF'
[program:connact]
command=/home/connact/Connact.ai/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 --timeout 120 --access-logfile - --error-logfile - app:app
directory=/home/connact/Connact.ai
user=connact
autostart=true
autorestart=true
stderr_logfile=/var/log/connact.err.log
stdout_logfile=/var/log/connact.out.log
environment=PATH="/home/connact/Connact.ai/venv/bin"
EOF

# 9. 配置 Nginx
echo -e "${GREEN}⚙️  步骤 9/10: 配置 Nginx（反向代理）...${NC}"
cat > /etc/nginx/sites-available/connact << 'EOF'
server {
    listen 80;
    server_name _;  # 改为你的域名，或保持 _ 使用 IP 访问

    client_max_body_size 16M;

    # 日志
    access_log /var/log/nginx/connact.access.log;
    error_log /var/log/nginx/connact.error.log;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时设置
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    # 静态文件缓存（如果有）
    location /static {
        alias /home/connact/Connact.ai/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 健康检查端点
    location /health {
        proxy_pass http://127.0.0.1:5000;
        access_log off;
    }
}
EOF

# 启用站点
ln -sf /etc/nginx/sites-available/connact /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 测试 Nginx 配置
echo -e "${GREEN}🧪 测试 Nginx 配置...${NC}"
nginx -t

# 10. 启动服务
echo -e "${GREEN}🚀 步骤 10/10: 启动服务...${NC}"
supervisorctl reread
supervisorctl update
supervisorctl restart connact 2>/dev/null || supervisorctl start connact
systemctl restart nginx

# 等待服务启动
sleep 3

# 检查服务状态
echo ""
echo "=========================================="
echo -e "${GREEN}✅ 部署完成！${NC}"
echo "=========================================="
echo ""

# 获取公网 IP
PUBLIC_IP=$(curl -s ifconfig.me || echo "无法获取")

echo -e "${GREEN}📋 下一步操作：${NC}"
echo ""
echo "1️⃣  配置 API Key（必须）："
echo "   nano /home/connact/Connact.ai/.env"
echo "   # 修改 GEMINI_API_KEY=实际的密钥"
echo ""
echo "2️⃣  重启应用："
echo "   supervisorctl restart connact"
echo ""
echo "3️⃣  查看服务状态："
echo "   supervisorctl status"
echo ""

# 检查服务状态
if supervisorctl status connact | grep -q RUNNING; then
    echo -e "${GREEN}✅ 应用正在运行${NC}"
    echo ""
    echo -e "${GREEN}🌐 访问地址：${NC}"
    echo "   http://${PUBLIC_IP}"
    echo ""
else
    echo -e "${RED}❌ 应用启动失败，请检查日志：${NC}"
    echo "   tail -f /var/log/connact.err.log"
fi

echo -e "${GREEN}📊 查看日志：${NC}"
echo "   tail -f /var/log/connact.out.log  # 应用日志"
echo "   tail -f /var/log/connact.err.log  # 错误日志"
echo ""

echo -e "${GREEN}🔧 常用命令：${NC}"
echo "   supervisorctl status             # 查看服务状态"
echo "   supervisorctl restart connact    # 重启应用"
echo "   systemctl restart nginx          # 重启 Nginx"
echo "   /home/connact/Connact.ai/update.sh  # 更新代码（见下方）"
echo ""

# 创建更新脚本
cat > /home/connact/update.sh << 'EOF'
#!/bin/bash
# Connact.ai 快速更新脚本

echo "🔄 开始更新 Connact.ai..."

cd /home/connact/Connact.ai

# 拉取最新代码
echo "📥 拉取最新代码..."
sudo -u connact git pull origin main

# 更新依赖
echo "📦 更新 Python 依赖..."
sudo -u connact ./venv/bin/pip install -r requirements.txt -q

# 重启应用
echo "🔄 重启应用..."
supervisorctl restart connact

# 等待启动
sleep 2

# 检查状态
if supervisorctl status connact | grep -q RUNNING; then
    echo "✅ 更新成功！应用正在运行"
    echo ""
    echo "📊 最近 20 行日志："
    tail -n 20 /var/log/connact.out.log
else
    echo "❌ 更新失败，请检查日志"
    tail -n 50 /var/log/connact.err.log
fi
EOF

chmod +x /home/connact/update.sh
chown connact:connact /home/connact/update.sh

echo -e "${YELLOW}💡 提示：${NC}"
echo "   - 创建了快速更新脚本：/home/connact/update.sh"
echo "   - 以后 git push 新代码后，在服务器执行：/home/connact/update.sh"
echo ""
echo "=========================================="
echo -e "${GREEN}🎉 祝使用愉快！${NC}"
echo "=========================================="

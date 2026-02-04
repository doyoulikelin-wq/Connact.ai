ls -la /var/data/
ls -la /var/data/users/
ls -la /var/data/prompt_logs/
ls -la /var/data/find_target_logs/

# 查看具体文件内容
cat /var/data/prompt_logs/2026-01-10/*.json
cat /var/data/find_target_logs//2026-01-15/*.json

# 查看数据库文件
ls -lh /var/data/

# 使用 SQLite 命令行查看数据
sqlite3 /var/data/app.db

# 在 SQLite 中执行查询
.tables                  # 列出所有表
.schema users            # 查看表结构
SELECT * FROM users;     # 查看所有用户
SELECT COUNT(*) FROM users;  # 用户总数
.exit                    # 退出
# 在 Render Dashboard 使用 Shell
cat /var/data/app.db | base64

# 复制输出，在本地执行
echo "粘贴的base64内容" | base64 -d > app.db

# 使用 SQLite GUI 工具打开
# Mac: DB Browser for SQLite (https://sqlitebrowser.org/)
# Windows: SQLiteStudio
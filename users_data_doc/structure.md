Render	/var/data/app.db	环境变量 DATA_DIR=/var/data
本地开发	./data/app.db	默认项目根目录下
阿里云	/home/connact/Connact.ai/data/app.db	部署脚本自动配置



SQLite 数据库结构
1. users - 用户基本信息
   - id (主键)
   - primary_email (主邮箱)
   - display_name (显示名称)
   - avatar_url (头像URL)
   - created_at (创建时间)
   - last_login_at (最后登录时间)
   - is_active (是否激活)
   - beta_access (Beta 访问权限)
   - beta_access_granted_at (Beta 授权时间)

2. auth_identities - 登录凭证（支持多种登录方式）
   - id (主键)
   - user_id (关联 users.id)
   - provider (登录方式: 'email' / 'google')
   - provider_sub (唯一标识)
   - email (邮箱)
   - password_hash (密码哈希，仅 email 登录)
   - email_verified (邮箱是否已验证)
   - created_at / last_used_at

3. user_profiles - 用户画像和偏好
   - user_id (主键，关联 users.id)
   - sender_profile_json (发件人画像 JSON)
   - preferences_json (用户偏好 JSON)
   - updated_at

4. email_verifications - 邮箱验证令牌
   - id / identity_id / token_hash
   - expires_at / used_at / created_at

5. login_events - 登录日志
   - user_id / provider / email
   - success / reason / ip / user_agent / created_at

6. waitlist - 候补名单
   - email / created_at / ip / user_agent

/var/data/
├── app.db          # SQLite 数据库
├── app.db-shm      # SQLite 共享内存文件
├── app.db-wal      # SQLite 写前日志（WAL 模式）
├── prompt_logs/    # 提示词日志
│   └── YYYY-MM-DD/
│       └── HHMMSS_*.json
├── find_target_logs/  # 目标推荐日志
│   └── YYYY-MM-DD/
└── users/          # 用户上传的文件
    └── YYYY-MM-DD/
        └── session_id/
            ├── resume.pdf
            ├── target_doc.pdf
            └── ...
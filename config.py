"""Global configuration values."""

import os
from pathlib import Path

# ============== 数据存储目录配置 ==============
# Render Disk 挂载路径，本地开发时使用项目根目录下的 data/
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    # 本地测试时可能没有权限创建 /var/data，跳过
    pass

# ============== Auth / 用户配置 ==============
# SQLite 数据库路径（默认放在 DATA_DIR 下）
DB_PATH = Path(os.environ.get("DB_PATH", str(DATA_DIR / "app.db")))

# Invite-only 注册：默认开启（生产推荐）
INVITE_ONLY = os.environ.get("INVITE_ONLY", "true").lower() in ("1", "true", "yes")

# Invite codes: 支持单个 INVITE_CODE 或多个 INVITE_CODES（逗号分隔）
_invite_codes_raw = os.environ.get("INVITE_CODES", "") or os.environ.get("INVITE_CODE", "")
INVITE_CODES = [c.strip() for c in _invite_codes_raw.split(",") if c.strip()]

# Internal beta: require invite code on every login attempt (Google + Email/Password)
_invite_required_for_login_raw = os.environ.get("INVITE_REQUIRED_FOR_LOGIN")
if _invite_required_for_login_raw is None:
    INVITE_REQUIRED_FOR_LOGIN = INVITE_ONLY
else:
    INVITE_REQUIRED_FOR_LOGIN = _invite_required_for_login_raw.lower() in ("1", "true", "yes")

# Email verification token 有效期（小时）
try:
    EMAIL_VERIFY_TTL_HOURS = int(os.environ.get("EMAIL_VERIFY_TTL_HOURS", "24"))
except ValueError:
    EMAIL_VERIFY_TTL_HOURS = 24

# ============== 邮件生成模型配置 ==============
# 全局开关：使用 OpenAI 作为所有 LLM 调用的后端（默认 true，因为 Gemini 配额用尽）
USE_OPENAI_AS_PRIMARY = os.environ.get("USE_OPENAI_AS_PRIMARY", "true").lower() in ("1", "true", "yes")

# 使用 OpenAI 还是 Gemini 生成邮件（默认使用 OpenAI GPT-4o）
USE_OPENAI_FOR_EMAIL = os.environ.get("USE_OPENAI_FOR_EMAIL", "true").lower() in ("1", "true", "yes")

# OpenAI 邮件生成模型
OPENAI_EMAIL_MODEL = os.environ.get("OPENAI_EMAIL_MODEL", "gpt-4o")

# OpenAI 通用模型（用于 profile 解析、问卷生成等）
OPENAI_DEFAULT_MODEL = os.environ.get("OPENAI_DEFAULT_MODEL", "gpt-4o")

# Default Gemini model (can be overridden via env)
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# Gemini model for recommendations with Google Search grounding
GEMINI_SEARCH_MODEL = os.environ.get("GEMINI_SEARCH_MODEL", "gemini-2.0-flash")

# Toggle Gemini Google Search grounding for recommendations - DISABLED (Gemini quota exceeded)
USE_GEMINI_SEARCH = os.environ.get("USE_GEMINI_SEARCH", "false").lower() in ("1", "true", "yes")

# Default model for recommendations (OpenAI) - disabled by default due to web_search incompatibility
RECOMMENDATION_MODEL = os.environ.get("OPENAI_RECOMMENDATION_MODEL", "gpt-4o")

# Toggle OpenAI built-in web_search for recommendations - DISABLED by default
# OpenAI API does not support 'web_search' tool type, causes errors
USE_OPENAI_WEB_SEARCH = os.environ.get("USE_OPENAI_WEB_SEARCH", "false").lower() in ("1", "true", "yes")

# Toggle using OpenAI for recommendations at all (fallback uses Gemini)
USE_OPENAI_RECOMMENDATIONS = os.environ.get("USE_OPENAI_RECOMMENDATIONS", "true").lower() in ("1", "true", "yes")

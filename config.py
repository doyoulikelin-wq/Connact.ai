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

# Developer invite codes: 开发者邀请码，使用这些码注册的用户自动获得开发者模式
_dev_codes_raw = os.environ.get("DEVELOPER_INVITE_CODES", "")
DEVELOPER_INVITE_CODES = [c.strip() for c in _dev_codes_raw.split(",") if c.strip()]

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

# ============== 开发者模式配置 ==============
# 开发者模式下可选的模型列表
# 价格格式: "input/output per 1M tokens"
# GPT-5系列自带adaptive thinking，复杂问题自动启用推理
# Thinking变体会生成内部推理tokens（按output计费），成本更高但推理更强
AVAILABLE_MODELS = {
    # Economy tier - 简单任务
    "gpt-4o-mini": {"name": "GPT-4o Mini", "price": "$0.15/$0.60", "tier": "economy"},
    "gpt-5-nano": {"name": "GPT-5 Nano", "price": "$0.05/$0.40", "tier": "economy"},
    "gpt-5-mini": {"name": "GPT-5 Mini", "price": "$0.25/$2.00", "tier": "economy"},
    # Standard tier - 通用任务（自带adaptive thinking）
    "gpt-4o": {"name": "GPT-4o", "price": "$2.50/$10.00", "tier": "standard"},
    "gpt-4.1": {"name": "GPT-4.1", "price": "$2.00/$8.00", "tier": "standard"},
    "gpt-5": {"name": "GPT-5", "price": "$1.25/$10.00", "tier": "standard"},
    "gpt-5.1": {"name": "GPT-5.1", "price": "$1.50/$12.00", "tier": "standard"},
    # Premium tier - 复杂任务
    "gpt-5.2": {"name": "GPT-5.2", "price": "$1.75/$14.00", "tier": "premium"},
    "gpt-5.2-pro": {"name": "GPT-5.2 Pro", "price": "$15.00/$120.00", "tier": "premium"},
    # Explicit Thinking - 显式推理模式（生成大量内部tokens）
    "gpt-5.1-thinking": {"name": "GPT-5.1 Thinking", "price": "$1.50/$12.00*", "tier": "thinking"},
    "gpt-5.2-thinking": {"name": "GPT-5.2 Thinking", "price": "$1.75/$14.00*", "tier": "thinking"},
    # Legacy reasoning models
    "o3-mini": {"name": "o3-mini", "price": "$1.10/$4.40", "tier": "reasoning"},
    "o3": {"name": "o3", "price": "$10.00/$40.00", "tier": "reasoning"},
    "o1": {"name": "o1", "price": "$15.00/$60.00", "tier": "reasoning"},
}

# 每个步骤的默认模型（普通用户和开发者未选择时使用）
# 推荐：大部分任务用economy/standard，不需要thinking
DEFAULT_STEP_MODELS = {
    "profile_extraction": "gpt-5-nano",      # 简单提取，不需要推理
    "questionnaire": "gpt-5-nano",           # 简单生成
    "answer_to_profile": "gpt-5-nano",       # 简单转换
    "find_recommendations": "gpt-5",         # 需要一定推理，standard足够
    "deep_search": "gpt-5-mini",             # 信息整合
    "generate_email": "gpt-5",               # 写作任务，standard足够
    "rewrite_email": "gpt-5-mini",           # 风格调整，简单任务
}

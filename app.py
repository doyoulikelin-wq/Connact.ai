"""Flask web application for Connact.ai."""

import logging
import os
import json
import tempfile
from pathlib import Path
from functools import wraps
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Optional

from dotenv import load_dotenv
load_dotenv()  # Load .env before anything else

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, make_response

# Configuration
import config

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Google OAuth
try:
    from flask_dance.contrib.google import make_google_blueprint, google
    GOOGLE_OAUTH_ENABLED = True
except ImportError:
    GOOGLE_OAUTH_ENABLED = False
    google = None

from src.services.auth_service import (
    auth_service,
    AuthError,
    AccountLockedError,
    InvalidCredentialsError,
    EmailNotVerifiedError,
    InviteRequiredError,
    InviteInvalidError,
    SignupDisabledError,
)

from src.email_agent import (
    SenderProfile,
    ReceiverProfile,
    generate_email,
    extract_profile_from_pdf,
    generate_questionnaire,
    generate_next_question,
    generate_next_target_question,
    build_profile_from_answers,
    find_target_recommendations,
    regenerate_email_with_style,
    enrich_receiver_with_deep_search,
)
from src.web_scraper import extract_person_profile_from_web

# Error notification
try:
    from src.services.error_notifier import error_notifier, notify_error
    ERROR_NOTIFICATION_ENABLED = True
except ImportError:
    ERROR_NOTIFICATION_ENABLED = False
    error_notifier = None
    notify_error = None

# User data service (contacts, emails, credits)
try:
    from src.services.user_data_service import user_data_service
    USER_DATA_ENABLED = True
except ImportError:
    USER_DATA_ENABLED = False
    user_data_service = None

# Apollo.io service (email lookup)
try:
    from src.services.apollo_service import lookup_contact_email
    APOLLO_ENABLED = True
except ImportError:
    APOLLO_ENABLED = False
    lookup_contact_email = None

# Prompt 数据收集
try:
    from src.services.prompt_collector import (
        prompt_collector,
        start_prompt_session,
        end_prompt_session,
        save_find_target_results,
    )
    PROMPT_COLLECTOR_ENABLED = True
except ImportError:
    PROMPT_COLLECTOR_ENABLED = False
    prompt_collector = None

# 用户上传数据存储
try:
    from src.services.user_uploads import (
        user_upload_storage,
        save_user_resume,
        save_user_targets,
        add_user_target,
    )
    USER_UPLOAD_ENABLED = True
except ImportError:
    USER_UPLOAD_ENABLED = False
    user_upload_storage = None

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# SECRET_KEY: require from environment in production; allow fallback only in dev
_secret_key = os.environ.get('SECRET_KEY', '')
if not _secret_key:
    if os.environ.get("FLASK_ENV", "").lower() == "production":
        raise RuntimeError("SECRET_KEY environment variable is required in production")
    _secret_key = 'dev-only-insecure-key-not-for-production'
    logger.warning("Using insecure default SECRET_KEY — set SECRET_KEY env var for production")
app.config['SECRET_KEY'] = _secret_key

# Rate limiting
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour"],
    storage_uri="memory://",
)

# Security headers (Flask-Talisman)
from flask_talisman import Talisman

_is_production = os.environ.get("FLASK_ENV", "").lower() == "production"
Talisman(
    app,
    force_https=_is_production,
    strict_transport_security=_is_production,
    content_security_policy=None,  # Set to a proper CSP dict when ready
    session_cookie_secure=_is_production,
    session_cookie_http_only=True,
    session_cookie_samesite="Lax",
)

# Input length limits
MAX_INPUT_LENGTH = 500
MAX_TEXT_LENGTH = 5000

# Allow OAuth over HTTP for local development (NEVER use in production!)
if os.environ.get("FLASK_ENV", "").lower() != "production" and os.environ.get("OAUTHLIB_INSECURE_TRANSPORT") is None:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

# Setup Google OAuth Blueprint
if GOOGLE_OAUTH_ENABLED and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    google_bp = make_google_blueprint(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scope=[
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
        ],
        redirect_to='google_callback',
    )
    app.register_blueprint(google_bp, url_prefix='/auth')
    GOOGLE_LOGIN_ENABLED = True
else:
    GOOGLE_LOGIN_ENABLED = False

# Store uploaded sender profile temporarily
sender_profile_cache = {}

# Version flag - set to 'v2' for new interface
APP_VERSION = os.environ.get('APP_VERSION', 'v2')
LANDING_VERSION = os.environ.get("LANDING_VERSION", "dark").strip().lower()


def login_required(f):
    """Decorator to require login for API endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def _validate_input_length(value: str | None, field_name: str, max_length: int = MAX_INPUT_LENGTH) -> str:
    """Validate and truncate input to max_length. Returns stripped string."""
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > max_length:
        raise ValueError(f"{field_name} exceeds maximum length of {max_length} characters")
    return text


def admin_required(f):
    """Decorator to require admin privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'error': 'Authentication required'}), 401
        
        user_email = session.get('user_email', '')
        if not config.is_admin(user_email):
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated_function


def _get_or_start_activity(
    user_id: str,
    activity_id: Optional[str] = None,
    *,
    title: Optional[str] = None,
) -> Optional[dict]:
    if not USER_DATA_ENABLED or not user_data_service or not user_id:
        return None

    activity_id = (activity_id or session.get("activity_id") or "").strip()
    if activity_id:
        session["activity_id"] = activity_id
        return {"id": activity_id}

    activity = user_data_service.start_activity(user_id, title=title)
    session["activity_id"] = activity["id"]
    return activity


def _log_activity_event(
    *,
    user_id: str,
    event_type: str,
    payload: Optional[dict] = None,
    activity_id: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[dict]:
    if not USER_DATA_ENABLED or not user_data_service or not user_id:
        return None

    activity = _get_or_start_activity(user_id, activity_id, title=title)
    if not activity:
        return None
    return user_data_service.add_activity_event(user_id, activity["id"], event_type, payload)


def _safe_redirect_url(url: Optional[str]) -> Optional[str]:
    url = (url or "").strip()
    if not url or not url.startswith("/"):
        return None
    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        return None
    return url


def _redirect_url_with_params(
    url: str,
    *,
    message: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    if message is not None:
        query["message"] = message
    if error is not None:
        query["error"] = error
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


# ============== Error Handlers ==============

@app.errorhandler(Exception)
def handle_exception(error):
    """Global exception handler - catches all unhandled errors."""
    # Always notify errors to WeChat Work
    if ERROR_NOTIFICATION_ENABLED and error_notifier:
        try:
            user_id = session.get('user_id', 'anonymous')
            request_path = request.path if request else 'unknown'
            
            # Extract request data safely
            context = {
                "method": request.method if request else None,
                "path": request_path,
                "args": dict(request.args) if request and request.args else None,
                "form_keys": list(request.form.keys()) if request and request.form else None,
            }
            
            # Try to get JSON data for API requests
            if request and request.path.startswith('/api/'):
                try:
                    json_data = request.get_json(silent=True)
                    if json_data:
                        # Only include non-sensitive keys
                        safe_keys = ['purpose', 'field', 'goal', 'name', 'session_id']
                        context['api_data'] = {k: json_data.get(k) for k in safe_keys if k in json_data}
                except:
                    pass
            
            error_notifier.notify_error(
                error=error,
                context=context,
                user_id=user_id,
                request_path=request_path,
            )
        except Exception as notify_err:
            # Don't let notification errors crash the app
            logger.error("WeChat notification failed: %s", notify_err)
    
    # Return JSON for API endpoints, HTML for pages
    if request and request.path.startswith('/api/'):
        return jsonify({
            'error': str(error),
            'type': type(error).__name__
        }), 500
    else:
        try:
            return render_template('error.html', error=str(error)), 500
        except:
            return f"<h1>Error</h1><p>{str(error)}</p>", 500


@app.errorhandler(404)
def handle_404(error):
    """Handle 404 errors."""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    return render_template('error.html', error='Page not found'), 404


@app.errorhandler(500)
def handle_500(error):
    """Handle 500 errors - delegates to global exception handler."""
    # Call the global exception handler for consistent error reporting
    return handle_exception(error)


# ============== Health Check ==============

@app.route('/healthz')
@limiter.exempt
def healthz():
    """Health check endpoint for load balancers and monitoring."""
    return jsonify({"status": "ok"}), 200


# ============== SEO Routes ==============

SITE_URL = os.environ.get('SITE_URL', 'https://coldemail-agent.onrender.com')

@app.route('/googledbbc30b4fd33789f.html')
def google_site_verification():
    return 'google-site-verification: googledbbc30b4fd33789f.html', 200, {'Content-Type': 'text/html'}

@app.route('/robots.txt')
def robots_txt():
    """Serve robots.txt for search engine crawlers."""
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /api/',
        'Disallow: /admin',
        'Disallow: /login',
        'Disallow: /signup',
        'Disallow: /logout',
        'Disallow: /verify-email',
        'Disallow: /resend-verification',
        'Disallow: /auth/',
        '',
        f'Sitemap: {SITE_URL}/sitemap.xml',
    ]
    return make_response('\n'.join(lines)), 200, {'Content-Type': 'text/plain'}


@app.route('/sitemap.xml')
def sitemap_xml():
    """Serve sitemap.xml for search engine indexing."""
    pages = [
        {'loc': '/', 'priority': '1.0', 'changefreq': 'weekly'},
        {'loc': '/access', 'priority': '0.6', 'changefreq': 'monthly'},
    ]
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for p in pages:
        xml_lines.append('  <url>')
        xml_lines.append(f'    <loc>{SITE_URL}{p["loc"]}</loc>')
        xml_lines.append(f'    <changefreq>{p["changefreq"]}</changefreq>')
        xml_lines.append(f'    <priority>{p["priority"]}</priority>')
        xml_lines.append('  </url>')
    xml_lines.append('</urlset>')
    return make_response('\n'.join(xml_lines)), 200, {'Content-Type': 'application/xml'}


# ============== Routes ==============

@app.route('/')
def index():
    """Render the main page."""
    if not session.get('user_id'):
        error = request.args.get("error")
        message = request.args.get("message")
        landing_variant = (request.args.get("landing") or LANDING_VERSION).strip().lower()
        landing_templates = {
            "substack": "landing.html",
            "legacy": "landing.html",
            "dark": "landing_dark.html",
            "futuristic": "landing_dark.html",
            "ib": "landing_dark.html",
        }
        landing_template = landing_templates.get(landing_variant, "landing_dark.html")
        safe_next = _safe_redirect_url(request.args.get("next"))
        next_params = {"next": safe_next} if safe_next and safe_next != url_for("index") else {}
        access_next_url = url_for("index", **next_params) + "#access"
        return render_template(
            landing_template,
            google_login_enabled=GOOGLE_LOGIN_ENABLED,
            error=error,
            message=message,
            invite_only=auth_service.invite_only,
            invite_required_for_login=auth_service.invite_required_for_login,
            invite_ok=bool(session.get("beta_invite_ok")),
            next_url=safe_next,
            access_next_url=access_next_url,
        )
    
    # Redirect admin users to admin dashboard
    user_email = session.get('user_email', '')
    if config.is_admin(user_email):
        return redirect(url_for('admin_dashboard'))
    
    # Use v2 template by default
    if APP_VERSION == 'v3':
        return render_template(
            'index_v3.html',
            user_email=session.get("user_email", ""),
            user_name=session.get("user_name", ""),
            user_picture=session.get("user_picture", ""),
        )
    elif APP_VERSION == 'v2':
        user_profile = auth_service.get_user_profile(session.get("user_id", "")) if session.get("user_id") else {}
        return render_template(
            'index_v2.html',
            user_email=session.get("user_email", ""),
            user_name=session.get("user_name", ""),
            user_picture=session.get("user_picture", ""),
            initial_sender_profile=user_profile.get("sender_profile"),
            initial_preferences=user_profile.get("preferences"),
        )
    return render_template(
        'index.html',
        user_email=session.get("user_email", ""),
        user_name=session.get("user_name", ""),
        user_picture=session.get("user_picture", ""),
    )


@app.route("/access", methods=["GET", "POST"])
def access():
    """Beta access gate: enter invite code or join waitlist."""
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method in ("GET", "HEAD"):
        error = request.args.get("error")
        message = request.args.get("message")
        safe_next = _safe_redirect_url(request.args.get("next"))
        target = url_for("index", **({"next": safe_next} if safe_next else {})) + "#access"
        return redirect(_redirect_url_with_params(target, message=message, error=error))

    next_url: Optional[str] = None
    if request.is_json:
        data = request.get_json() or {}
        invite_code = (data.get("invite_code", "") or "").strip()
        next_url = (data.get("next") or data.get("next_url") or "")
    else:
        invite_code = (request.form.get("invite_code", "") or "").strip()
        next_url = request.form.get("next") or request.args.get("next")

    try:
        auth_service.validate_invite_code(invite_code)
        session["beta_invite_ok"] = True
        session["beta_invite_code"] = invite_code
        session.permanent = True
        if request.is_json:
            return jsonify({"success": True})
        safe_next = _safe_redirect_url(next_url) or f"{url_for('index')}#access"
        message = "Invite code verified. You can sign in or create an account."
        return redirect(_redirect_url_with_params(safe_next, message=message))
    except AuthError as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 400
        safe_next = _safe_redirect_url(next_url)
        if safe_next:
            return redirect(_redirect_url_with_params(safe_next, error=str(e)))
        return redirect(_redirect_url_with_params(f"{url_for('index')}#access", error=str(e)))


@app.route("/waitlist", methods=["POST"])
def waitlist():
    """Join waitlist by leaving an email address."""
    next_url: Optional[str] = None
    if request.is_json:
        data = request.get_json() or {}
        email = (data.get("email", "") or "").strip()
        next_url = (data.get("next") or data.get("next_url") or "")
    else:
        email = (request.form.get("email", "") or "").strip()
        next_url = request.form.get("next") or request.args.get("next")

    try:
        created = auth_service.add_waitlist_email(
            email,
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        message = "Thanks! You’re on the waitlist." if created else "You’re already on the waitlist."
        if request.is_json:
            return jsonify({"success": True, "created": created})
        safe_next = _safe_redirect_url(next_url)
        if safe_next:
            return redirect(_redirect_url_with_params(safe_next, message=message))
        return redirect(_redirect_url_with_params(f"{url_for('index')}#access", message=message))
    except AuthError as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 400
        safe_next = _safe_redirect_url(next_url)
        if safe_next:
            return redirect(_redirect_url_with_params(safe_next, error=str(e)))
        return redirect(_redirect_url_with_params(f"{url_for('index')}#access", error=str(e)))


@app.route('/v3')
def index_v3():
    """Render the v3 interface for testing."""
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return render_template('index_v3.html')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per 5 minutes", methods=["POST"])
def login():
    """Handle login."""
    if request.method in ('GET', 'HEAD'):
        if session.get('user_id'):
            return redirect(url_for('index'))

        next_url = _safe_redirect_url(request.args.get("next"))
        if next_url:
            session["post_login_next"] = next_url
        else:
            next_url = _safe_redirect_url(session.get("post_login_next"))

        error = request.args.get("error")
        message = request.args.get("message")
        return render_template(
            'login.html',
            google_login_enabled=GOOGLE_LOGIN_ENABLED,
            error=error,
            message=message,
            invite_only=auth_service.invite_only,
            invite_required_for_login=auth_service.invite_required_for_login,
            invite_ok=bool(session.get("beta_invite_ok")),
            next_url=next_url,
        )
    
    # Handle POST - check for both JSON and form data (email/password login)
    next_url: Optional[str] = None
    if request.is_json:
        data = request.get_json()
        email = (data.get('email', '') or '').strip()
        password = data.get('password', '')
        invite_code = (data.get("invite_code", "") or "").strip()
        next_url = (data.get("next") or data.get("next_url") or "")
    else:
        email = (request.form.get('email', '') or '').strip()
        password = request.form.get('password', '')
        invite_code = (request.form.get("invite_code", "") or "").strip()
        next_url = request.form.get("next") or request.args.get("next")

    safe_next = _safe_redirect_url(next_url) or _safe_redirect_url(session.get("post_login_next"))
    
    try:
        invite_ok = bool(session.get("beta_invite_ok"))
        if not invite_code:
            invite_code = (session.get("beta_invite_code") or "").strip()

        if auth_service.invite_required_for_login and not invite_ok:
            user_id = auth_service.get_user_id_for_password_email(email)
            if user_id and auth_service.user_has_beta_access(user_id):
                invite_ok = True
                session["beta_invite_ok"] = True
                session.permanent = True
            else:
                if invite_code:
                    auth_service.validate_invite_code(invite_code)
                    session["beta_invite_ok"] = True
                    session["beta_invite_code"] = invite_code
                    session.permanent = True
                    invite_ok = True
                else:
                    if request.is_json:
                        return jsonify({"error": "Invite code required"}), 403
                    params = {"error": "Invite code required."}
                    if safe_next:
                        params["next"] = safe_next
                    return redirect(url_for("access", **params))

        user = auth_service.authenticate_password(
            email=email,
            password=password,
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        # Grant beta access after the first successful invite-gated login.
        if auth_service.invite_required_for_login and not auth_service.user_has_beta_access(user.id) and invite_ok:
            auth_service.grant_beta_access(user.id)

        session["user_id"] = user.id
        session["user_email"] = user.primary_email or email
        session["user_name"] = user.display_name or ""
        session["user_picture"] = user.avatar_url or ""
        session["login_method"] = "password"
        session.permanent = True
        session.pop("post_login_next", None)
        if request.is_json:
            return jsonify({"success": True, "redirect_url": safe_next or url_for("index")})
        return redirect(safe_next or url_for("index"))
    except EmailNotVerifiedError:
        if request.is_json:
            return jsonify({"error": "Email not verified", "code": "email_not_verified"}), 403
        params = {"error": "Email not verified. Please verify your email first."}
        if safe_next:
            params["next"] = safe_next
        return redirect(url_for("login", **params))
    except AccountLockedError as e:
        if request.is_json:
            return jsonify({"error": str(e), "code": "account_locked"}), 429
        params = {"error": str(e)}
        if safe_next:
            params["next"] = safe_next
        return redirect(url_for("login", **params))
    except InvalidCredentialsError:
        if request.is_json:
            return jsonify({"error": "Invalid email or password"}), 401
        params = {"error": "Invalid email or password."}
        if safe_next:
            params["next"] = safe_next
        return redirect(url_for("login", **params))
    except AuthError as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 400
        params = {"error": str(e)}
        if safe_next:
            params["next"] = safe_next
        return redirect(url_for("login", **params))


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per 5 minutes", methods=["POST"])
def signup():
    """Invite-only signup for email/password accounts (requires email verification)."""
    if request.method in ("GET", "HEAD"):
        if session.get("user_id"):
            return redirect(url_for("index"))
        next_url = _safe_redirect_url(request.args.get("next"))
        if next_url:
            session["post_login_next"] = next_url
        else:
            next_url = _safe_redirect_url(session.get("post_login_next"))
        invite_ok = bool(session.get("beta_invite_ok"))
        invite_code = (session.get("beta_invite_code") or "").strip()
        if auth_service.invite_required_for_login and not invite_ok:
            params = {"message": "Enter an invite code to continue."}
            if next_url:
                params["next"] = next_url
            return redirect(url_for("access", **params))
        if auth_service.invite_only and not invite_code:
            params = {"message": "Enter an invite code to sign up."}
            if next_url:
                params["next"] = next_url
            return redirect(url_for("access", **params))
        error = request.args.get("error")
        message = request.args.get("message")
        return render_template(
            "signup.html",
            google_login_enabled=GOOGLE_LOGIN_ENABLED,
            error=error,
            message=message,
            invite_only=auth_service.invite_only,
            invite_required_for_login=auth_service.invite_required_for_login,
            invite_ok=invite_ok,
            next_url=next_url,
        )

    next_url: Optional[str] = None
    if request.is_json:
        data = request.get_json()
        email = (data.get("email", "") or "").strip()
        password = data.get("password", "") or ""
        display_name = (data.get("name", "") or "").strip()
        invite_code = (data.get("invite_code", "") or "").strip()
        next_url = (data.get("next") or data.get("next_url") or "")
    else:
        email = (request.form.get("email", "") or "").strip()
        password = request.form.get("password", "") or ""
        display_name = (request.form.get("name", "") or "").strip()
        invite_code = (request.form.get("invite_code", "") or "").strip()
        next_url = request.form.get("next") or request.args.get("next")

    safe_next = _safe_redirect_url(next_url)
    if safe_next:
        session["post_login_next"] = safe_next

    try:
        invite_ok = bool(session.get("beta_invite_ok"))
        if not invite_code:
            invite_code = (session.get("beta_invite_code") or "").strip()

        if auth_service.invite_required_for_login and not invite_ok:
            if invite_code:
                auth_service.validate_invite_code(invite_code)
                session["beta_invite_ok"] = True
                session["beta_invite_code"] = invite_code
                session.permanent = True
                invite_ok = True
            else:
                if request.is_json:
                    return jsonify({"error": "Invite code required"}), 403
                params = {"error": "Invite code required."}
                if safe_next:
                    params["next"] = safe_next
                return redirect(url_for("access", **params))

        if auth_service.invite_only and not invite_code:
            if request.is_json:
                return jsonify({"error": "Invite code required"}), 403
            params = {"error": "Invite code required."}
            if safe_next:
                params["next"] = safe_next
            return redirect(url_for("access", **params))

        verification = auth_service.create_password_user(
            email=email,
            password=password,
            display_name=display_name or None,
            invite_code=invite_code or None,
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        if auth_service.invite_required_for_login and invite_ok:
            user_id = auth_service.get_user_id_for_password_email(email)
            if user_id:
                auth_service.grant_beta_access(user_id)

        # Send verification email if SMTP is configured; otherwise show link on screen (dev/local).
        verification_link = url_for("verify_email", token=verification.token, _external=True)
        email_sent = _send_verification_email(verification.email, verification_link)

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "email_sent": email_sent,
                    "verification_link": None if email_sent else verification_link,
                }
            )
        message = "Account created. Please verify your email to log in."
        if not email_sent:
            message += " (Email sending not configured; use the verification link below.)"
        return render_template(
            "signup_done.html",
            message=message,
            email=verification.email,
            email_sent=email_sent,
            verification_link=None if email_sent else verification_link,
            next_url=safe_next,
        )
    except (InviteRequiredError, InviteInvalidError, SignupDisabledError) as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 403
        params = {"error": str(e)}
        if safe_next:
            params["next"] = safe_next
        return redirect(url_for("signup", **params))
    except AuthError as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 400
        params = {"error": str(e)}
        if safe_next:
            params["next"] = safe_next
        return redirect(url_for("signup", **params))


@app.route("/verify-email")
def verify_email():
    """Verify email for password accounts."""
    token = request.args.get("token", "")
    user_id = auth_service.verify_email_token(token)
    next_url = _safe_redirect_url(session.get("post_login_next"))
    if user_id:
        params = {"message": "Email verified. You can now log in."}
        if next_url:
            params["next"] = next_url
        return redirect(url_for("login", **params))
    params = {"error": "Invalid or expired verification link."}
    if next_url:
        params["next"] = next_url
    return redirect(url_for("login", **params))


@app.route("/resend-verification", methods=["POST"])
def resend_verification():
    """Resend email verification for password accounts."""
    if request.is_json:
        data = request.get_json()
        email = (data.get("email", "") or "").strip()
    else:
        email = (request.form.get("email", "") or "").strip()
    try:
        verification = auth_service.resend_email_verification(
            email=email,
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        verification_link = url_for("verify_email", token=verification.token, _external=True)
        email_sent = _send_verification_email(verification.email, verification_link)
        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "email_sent": email_sent,
                    "verification_link": None if email_sent else verification_link,
                }
            )
        message = "Verification email resent."
        if not email_sent:
            message += " (Email sending not configured; use the verification link below.)"
        next_url = _safe_redirect_url(session.get("post_login_next"))
        return render_template(
            "signup_done.html",
            message=message,
            email=verification.email,
            email_sent=email_sent,
            verification_link=None if email_sent else verification_link,
            next_url=next_url,
        )
    except AuthError as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 400
        params = {"error": str(e)}
        next_url = _safe_redirect_url(session.get("post_login_next"))
        if next_url:
            params["next"] = next_url
        return redirect(url_for("login", **params))


@app.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback."""
    if not GOOGLE_LOGIN_ENABLED:
        return redirect(url_for('login'))
    
    if not google.authorized:
        return redirect(url_for('google.login'))
    
    try:
        # Prefer stable OIDC subject via id_token if available; fallback to userinfo.
        claims = None
        token = getattr(google, "token", None) or {}
        id_token_str = token.get("id_token")
        if id_token_str and GOOGLE_CLIENT_ID:
            try:
                from google.oauth2 import id_token as google_id_token
                from google.auth.transport import requests as google_requests

                claims = google_id_token.verify_oauth2_token(
                    id_token_str,
                    google_requests.Request(),
                    GOOGLE_CLIENT_ID,
                )
            except Exception:
                claims = None

        if not claims:
            resp = google.get("/oauth2/v2/userinfo")
            if resp.ok:
                claims = resp.json()

        if not claims:
            raise Exception("Failed to fetch Google user info.")

        google_sub = claims.get("sub") or claims.get("id") or ""
        email = claims.get("email")
        name = claims.get("name")
        picture = claims.get("picture")
        email_verified = claims.get("email_verified")

        invite_code = (session.get("beta_invite_code") or "").strip() or None
        pending_invite_code = (session.pop("pending_invite_code", None) or "").strip() or None
        if not invite_code and pending_invite_code:
            invite_code = pending_invite_code

        invite_ok = bool(session.get("beta_invite_ok"))
        existing_user_id = auth_service.get_user_id_for_google_sub(google_sub)
        if not existing_user_id and email and (email_verified is True):
            existing_user_id = auth_service.get_user_id_for_password_email(email)

        if auth_service.invite_required_for_login and not invite_ok:
            if existing_user_id and auth_service.user_has_beta_access(existing_user_id):
                invite_ok = True
                session["beta_invite_ok"] = True
                session.permanent = True
            elif invite_code:
                try:
                    auth_service.validate_invite_code(invite_code)
                    session["beta_invite_ok"] = True
                    session["beta_invite_code"] = invite_code
                    session.permanent = True
                    invite_ok = True
                except AuthError as e:
                    params = {"error": str(e)}
                    safe_next = _safe_redirect_url(session.get("post_login_next"))
                    if safe_next:
                        params["next"] = safe_next
                    return redirect(url_for("access", **params))
            else:
                params = {"error": "Invite code required."}
                safe_next = _safe_redirect_url(session.get("post_login_next"))
                if safe_next:
                    params["next"] = safe_next
                return redirect(url_for("access", **params))

        if auth_service.invite_only and not existing_user_id and not invite_code:
            params = {"error": "Invite code required."}
            safe_next = _safe_redirect_url(session.get("post_login_next"))
            if safe_next:
                params["next"] = safe_next
            return redirect(url_for("access", **params))

        user = auth_service.authenticate_google(
            google_sub=google_sub,
            email=email,
            display_name=name,
            avatar_url=picture,
            email_verified=bool(email_verified) if email_verified is not None else None,
            invite_code=invite_code,
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        if auth_service.invite_required_for_login:
            if invite_ok:
                auth_service.grant_beta_access(user.id)
            if auth_service.user_has_beta_access(user.id):
                session["beta_invite_ok"] = True
                session.permanent = True

        session["user_id"] = user.id
        session["user_email"] = user.primary_email or (email or "")
        session["user_name"] = user.display_name or (name or "")
        session["user_picture"] = user.avatar_url or (picture or "")
        session["login_method"] = "google"
        session.permanent = True
        redirect_url = _safe_redirect_url(session.pop("post_login_next", None))
        return redirect(redirect_url or url_for("index"))
    except Exception as e:
        logger.error("Google OAuth error: %s", e)
        if isinstance(e, (InviteRequiredError, InviteInvalidError, SignupDisabledError)):
            params = {"error": str(e)}
            safe_next = _safe_redirect_url(session.get("post_login_next"))
            if safe_next:
                params["next"] = safe_next
            return redirect(url_for("login", **params))
    
    return redirect(url_for('login'))


@app.route('/logout')
def logout():
    """Handle logout."""
    session.pop("user_id", None)
    session.pop('user_email', None)
    session.pop('user_name', None)
    session.pop('user_picture', None)
    session.pop('login_method', None)
    session.pop("post_login_next", None)
    return redirect(url_for('index'))


# ====================================================================
# Admin Routes - 管理员功能
# ====================================================================

@app.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard - only accessible to admin users."""
    user_email = session.get('user_email', '')
    
    if not config.is_admin(user_email):
        # Redirect non-admin users to regular dashboard
        return redirect(url_for('v3'))
    
    return render_template('admin.html', 
                         user_email=user_email,
                         app_version=APP_VERSION)


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_list_users():
    """Get list of all users with credits info."""
    try:
        import sqlite3
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        
        query = """
        SELECT 
            u.id as user_id,
            u.primary_email as email,
            u.display_name,
            COALESCE(v.is_verified, 0) as is_verified,
            u.created_at,
            u.last_login_at,
            COALESCE(c.apollo_credits, 5) as apollo_credits,
            COALESCE(c.total_used, 0) as total_used,
            c.last_used_at
        FROM users u
        LEFT JOIN (
            SELECT user_id, MAX(email_verified) as is_verified
            FROM auth_identities
            GROUP BY user_id
        ) v ON u.id = v.user_id
        LEFT JOIN user_credits c ON u.id = c.user_id
        ORDER BY u.created_at DESC
        """
        
        users = []
        for row in conn.execute(query).fetchall():
            users.append({
                'user_id': row['user_id'],
                'email': row['email'],
                'display_name': row['display_name'],
                'is_verified': bool(row['is_verified']),
                'created_at': row['created_at'],
                'last_login_at': row['last_login_at'],
                'credits': {
                    'apollo_credits': row['apollo_credits'],
                    'total_used': row['total_used'],
                    'last_used_at': row['last_used_at']
                }
            })
        
        conn.close()
        return jsonify({'success': True, 'users': users})
        
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'operation': 'admin_list_users'},
                user_id=session.get('user_id'),
                request_path='/api/admin/users'
            )
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/user/<user_id>/credits', methods=['GET'])
@admin_required
def api_admin_get_user_credits(user_id):
    """Get detailed credits info for a specific user."""
    try:
        if not user_data_service:
            return jsonify({'error': 'User data service not available'}), 500
        
        credits = user_data_service.get_user_credits(user_id)
        return jsonify({
            'success': True,
            'credits': {
                'apollo_credits': credits.apollo_credits,
                'total_used': credits.total_used,
                'last_used_at': credits.last_used_at
            }
        })
        
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'operation': 'admin_get_credits', 'target_user': user_id},
                user_id=session.get('user_id'),
                request_path=f'/api/admin/user/{user_id}/credits'
            )
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/user/<user_id>/add-credits', methods=['POST'])
@admin_required
def api_admin_add_credits(user_id):
    """Add credits to a user's account."""
    try:
        data = request.get_json() or {}
        amount = data.get('amount', 0)
        
        if not isinstance(amount, int) or amount <= 0:
            return jsonify({'error': 'Amount must be a positive integer'}), 400
        
        if not user_data_service:
            return jsonify({'error': 'User data service not available'}), 500
        
        new_total = user_data_service.add_credits(user_id, amount)
        
        return jsonify({
            'success': True,
            'message': f'Added {amount} credits',
            'new_total': new_total
        })
        
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'operation': 'admin_add_credits', 'target_user': user_id, 'amount': amount},
                user_id=session.get('user_id'),
                request_path=f'/api/admin/user/{user_id}/add-credits'
            )
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/user/<user_id>/info', methods=['GET'])
@admin_required
def api_admin_user_info(user_id):
    """Get detailed information about a user."""
    try:
        # Get user basic info
        user = auth_service.get_user(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        import sqlite3
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        verified_row = conn.execute(
            "SELECT MAX(email_verified) as is_verified FROM auth_identities WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        conn.close()
        is_verified = bool(verified_row["is_verified"]) if verified_row else False
        
        # Get credits
        credits = None
        if user_data_service:
            credits = user_data_service.get_user_credits(user_id)
        
        # Get dashboard data (contacts, emails)
        dashboard = None
        if user_data_service:
            dashboard = user_data_service.get_user_dashboard(user_id)

        # Get activity dates
        activity_dates = None
        if user_data_service:
            activity_dates = user_data_service.get_user_activity_dates(user_id)
        
        return jsonify({
            'success': True,
            'user': {
                'user_id': user.id,
                'email': user.primary_email,
                'display_name': user.display_name,
                'is_verified': is_verified,
                'created_at': user.created_at,
                'last_login_at': user.last_login_at
            },
            'credits': {
                'apollo_credits': credits.apollo_credits if credits else 5,
                'total_used': credits.total_used if credits else 0,
                'last_used_at': credits.last_used_at if credits else None
            } if credits else None,
            'usage': {
                'saved_contacts': len(dashboard.get('contacts', [])) if dashboard else 0,
                'generated_emails': len(dashboard.get('emails', [])) if dashboard else 0
            } if dashboard else None,
            'activity_dates': activity_dates or [],
        })
        
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'operation': 'admin_user_info', 'target_user': user_id},
                user_id=session.get('user_id'),
                request_path=f'/api/admin/user/{user_id}/info'
            )
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/user/<user_id>/date/<date>', methods=['GET'])
@admin_required
def api_admin_user_date_activities(user_id, date):
    """Get detailed activities for a specific date."""
    try:
        if not user_data_service:
            return jsonify({'error': 'User data service not available'}), 500
        
        activities = user_data_service.get_user_activities_by_date(user_id, date)
        
        return jsonify({
            'success': True,
            'date': date,
            'activities': activities
        })
        
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'operation': 'admin_user_date_activities', 'target_user': user_id, 'date': date},
                user_id=session.get('user_id'),
                request_path=f'/api/admin/user/{user_id}/date/{date}'
            )
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/user/<user_id>/export', methods=['GET'])
@admin_required
def api_admin_user_export(user_id):
    """Export all user data as JSON."""
    try:
        # Get user basic info
        user = auth_service.get_user(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        import sqlite3
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        verified_row = conn.execute(
            "SELECT MAX(email_verified) as is_verified FROM auth_identities WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        conn.close()
        is_verified = bool(verified_row["is_verified"]) if verified_row else False
        
        # Get all data
        credits = None
        dashboard = None
        all_activities = []
        activity_dates = []
        
        if user_data_service:
            credits = user_data_service.get_user_credits(user_id)
            dashboard = user_data_service.get_user_dashboard(user_id)
            activity_dates = user_data_service.get_user_activity_dates(user_id)
            # Get all activities (no limit)
            all_activities = user_data_service.get_user_activities(user_id, limit=1000)
        
        export_data = {
            'user': {
                'user_id': user.id,
                'email': user.primary_email,
                'display_name': user.display_name,
                'is_verified': is_verified,
                'created_at': user.created_at,
                'last_login_at': user.last_login_at
            },
            'credits': {
                'apollo_credits': credits.apollo_credits if credits else 5,
                'total_used': credits.total_used if credits else 0,
                'last_used_at': credits.last_used_at if credits else None
            } if credits else None,
            'usage': {
                'saved_contacts': len(dashboard.get('contacts', [])) if dashboard else 0,
                'generated_emails': len(dashboard.get('emails', [])) if dashboard else 0,
                'contacts': dashboard.get('contacts', []) if dashboard else [],
                'emails': dashboard.get('emails', []) if dashboard else []
            } if dashboard else None,
            'activity_dates': activity_dates or [],
            'activities': all_activities,
            'exported_at': datetime.now().isoformat()
        }
        
        # Return as JSON file download
        from flask import make_response
        response = make_response(json.dumps(export_data, ensure_ascii=False, indent=2))
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=user_{user_id}_export.json'
        
        return response
        
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'operation': 'admin_user_export', 'target_user': user_id},
                user_id=session.get('user_id'),
                request_path=f'/api/admin/user/{user_id}/export'
            )
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/errors', methods=['GET'])
@admin_required
def api_admin_list_errors():
    """Get list of all error logs."""
    try:
        import sqlite3
        from datetime import datetime, timedelta
        
        # Get query parameters
        limit = min(int(request.args.get('limit', 100)), 500)
        offset = int(request.args.get('offset', 0))
        show_resolved = request.args.get('show_resolved', 'false').lower() == 'true'
        
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Build query
        where_clause = "" if show_resolved else "WHERE resolved_at IS NULL"
        
        query = f"""
        SELECT 
            id,
            error_type,
            error_message,
            request_path,
            user_id,
            context,
            created_at,
            resolved_at,
            resolved_by,
            notes
        FROM error_logs
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """
        
        errors = []
        for row in conn.execute(query, (limit, offset)).fetchall():
            import json
            errors.append({
                'id': row['id'],
                'error_type': row['error_type'],
                'error_message': row['error_message'],
                'request_path': row['request_path'],
                'user_id': row['user_id'],
                'context': json.loads(row['context']) if row['context'] else None,
                'created_at': row['created_at'],
                'resolved_at': row['resolved_at'],
                'resolved_by': row['resolved_by'],
                'notes': row['notes']
            })
        
        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM error_logs {where_clause}"
        total = conn.execute(count_query).fetchone()['total']
        
        conn.close()
        
        return jsonify({
            'success': True,
            'errors': errors,
            'total': total,
            'limit': limit,
            'offset': offset
        })
        
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'operation': 'admin_list_errors'},
                user_id=session.get('user_id'),
                request_path='/api/admin/errors'
            )
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/error/<int:error_id>/resolve', methods=['POST'])
@admin_required
def api_admin_resolve_error(error_id):
    """Mark an error as resolved."""
    try:
        import sqlite3
        from datetime import datetime
        
        data = request.get_json() or {}
        notes = data.get('notes', '')
        
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        
        admin_email = session.get('user_email', '')
        resolved_at = datetime.now().isoformat()
        
        cursor.execute("""
            UPDATE error_logs
            SET resolved_at = ?,
                resolved_by = ?,
                notes = ?
            WHERE id = ?
        """, (resolved_at, admin_email, notes, error_id))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Error log not found'}), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Error marked as resolved'
        })
        
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'operation': 'admin_resolve_error', 'error_id': error_id},
                user_id=session.get('user_id'),
                request_path=f'/api/admin/error/{error_id}/resolve'
            )
        return jsonify({'error': str(e)}), 500


@app.route("/login/google")
def google_login_start():
    """Start Google OAuth flow (stores optional invite code in session for new users)."""
    if not GOOGLE_LOGIN_ENABLED:
        return redirect(url_for("login"))
    next_url = _safe_redirect_url(request.args.get("next"))
    if next_url:
        session["post_login_next"] = next_url
    invite_code = (request.args.get("invite_code", "") or "").strip()
    if invite_code:
        try:
            auth_service.validate_invite_code(invite_code)
            session["beta_invite_ok"] = True
            session["beta_invite_code"] = invite_code
            session["pending_invite_code"] = invite_code
            session.permanent = True
        except AuthError as e:
            params = {"error": str(e)}
            if next_url:
                params["next"] = next_url
            return redirect(url_for("access", **params))
    return redirect(url_for("google.login"))


@app.route("/api/me")
@login_required
def api_me():
    """Return current user basic info."""
    user_id = session.get("user_id", "")
    user = auth_service.get_user(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(
        {
            "success": True,
            "user": {
                "id": user.id,
                "email": user.primary_email,
                "name": user.display_name,
                "picture": user.avatar_url,
                "last_login_at": user.last_login_at,
            },
        }
    )


@app.route("/api/profile", methods=["GET", "POST"])
@login_required
def api_profile():
    """Get or update current user's persisted profile."""
    user_id = session.get("user_id", "")
    if request.method == "GET":
        profile = auth_service.get_user_profile(user_id)
        return jsonify({"success": True, **profile})

    data = request.get_json() or {}
    sender_profile = data.get("sender_profile")
    preferences = data.get("preferences")
    auth_service.update_user_profile(
        user_id=user_id,
        sender_profile=sender_profile if isinstance(sender_profile, dict) else None,
        preferences=preferences if isinstance(preferences, dict) else None,
    )
    return jsonify({"success": True})


@app.route("/api/submit-survey", methods=["POST"])
def api_submit_survey():
    """Save user survey response (how they heard about us)."""
    import sqlite3
    from datetime import datetime
    
    data = request.get_json() or {}
    source = data.get("source", "").strip()
    email = data.get("email", "").strip()
    
    if not source:
        return jsonify({"error": "Source is required"}), 400
    
    conn = None
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        
        # Create survey_responses table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS survey_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                email TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # Insert survey response
        cursor.execute(
            """
            INSERT INTO survey_responses (source, email, ip_address, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                source,
                email or None,
                request.remote_addr,
                request.headers.get("User-Agent"),
                datetime.utcnow().isoformat(),
            ),
        )
        
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.warning("Error saving survey response: %s", e)
        if conn:
            conn.rollback()
        return jsonify({"error": "Failed to save survey response"}), 500
    finally:
        if conn:
            conn.close()


def _send_verification_email(to_email: str, verification_link: str) -> bool:
    """Send email verification link via SMTP if configured.

    Configure with:
      SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        logger.info("Verification email link generated for %s", to_email)
        return False

    import smtplib
    from email.message import EmailMessage

    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        port = 587
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    from_email = os.environ.get("SMTP_FROM", "").strip() or username or "no-reply@example.com"

    msg = EmailMessage()
    msg["Subject"] = "Verify your email"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(
        "Welcome!\n\nPlease verify your email by opening this link:\n\n"
        f"{verification_link}\n\n"
        "If you didn't request this, you can ignore this email.\n"
    )

    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        if username and password:
            server.login(username, password)
        server.send_message(msg)
    return True


@app.route('/api/upload-sender-pdf', methods=['POST'])
@login_required
def upload_sender_pdf():
    """Upload and parse sender PDF resume."""
    if 'pdf' not in request.files:
        return jsonify({'error': 'No PDF file uploaded'}), 400
    
    pdf_file = request.files['pdf']
    if pdf_file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not pdf_file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'File must be a PDF'}), 400
    
    try:
        # Get session ID
        session_id = request.form.get('session_id', 'default')
        original_filename = pdf_file.filename
        
        # 保存用户上传的原始 PDF 文件
        if USER_UPLOAD_ENABLED and user_upload_storage:
            # 先保存原始 PDF
            user_upload_storage.save_resume_pdf(session_id, pdf_file, original_filename)
            # 重置文件指针以便后续读取
            pdf_file.seek(0)
        
        # Save to temp file and extract profile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            pdf_file.save(tmp.name)
            profile = extract_profile_from_pdf(Path(tmp.name))
            os.unlink(tmp.name)  # Clean up temp file
        
        # Cache the extracted profile
        profile_dict = {
            'name': profile.name,
            'raw_text': profile.raw_text,
            'education': profile.education,
            'experiences': profile.experiences,
            'skills': profile.skills,
            'projects': profile.projects,
        }
        sender_profile_cache[session_id] = profile_dict

        # Persist to the logged-in user's profile (for future sessions)
        user_id = session.get("user_id", "")
        if user_id:
            auth_service.update_user_profile(user_id=user_id, sender_profile=profile_dict)

        _log_activity_event(
            user_id=user_id,
            event_type='resume_upload',
            payload={
                'filename': original_filename,
                'session_id': session_id,
                'profile': {
                    'name': profile.name,
                    'education': profile.education,
                    'experiences': profile.experiences,
                    'skills': profile.skills,
                    'projects': profile.projects,
                    'raw_text_length': len(profile.raw_text or ''),
                },
            },
        )

        # 保存解析后的简历数据
        if USER_UPLOAD_ENABLED and user_upload_storage:
            user_upload_storage.save_resume_profile(session_id, profile_dict)
            # Attach user identity info to this upload session (best-effort)
            user_upload_storage.update_user_info(
                session_id,
                {
                    "user_id": user_id,
                    "user_email": session.get("user_email", ""),
                    "login_method": session.get("login_method", ""),
                },
            )
        
        return jsonify({
            'success': True,
            'profile': profile_dict
        })
    
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'filename': pdf_file.filename if 'pdf_file' in locals() else 'unknown'},
                user_id=session.get('user_id'),
                request_path='/api/upload-sender-pdf',
            )
        return jsonify({'error': str(e)}), 500


@app.route('/api/search-receiver', methods=['POST'])
@login_required
@limiter.limit("12 per hour")
def search_receiver():
    """Search for receiver information from the web."""
    data = request.get_json()
    
    try:
        name = _validate_input_length(data.get('name', ''), 'name')
        field = _validate_input_length(data.get('field', ''), 'field')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    if not name:
        return jsonify({'error': 'Receiver name is required'}), 400
    if not field:
        return jsonify({'error': 'Receiver field is required'}), 400
    
    try:
        scraped_info = extract_person_profile_from_web(
            name=name,
            field=field,
            max_pages=3,
        )
        
        return jsonify({
            'success': True,
            'profile': {
                'name': scraped_info.name,
                'field': scraped_info.field,
                'raw_text': scraped_info.raw_text,
                'education': scraped_info.education,
                'experiences': scraped_info.experiences,
                'skills': scraped_info.skills,
                'projects': scraped_info.projects,
                'sources': scraped_info.sources,
            }
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-email', methods=['POST'])
@login_required
@limiter.limit("12 per hour")
def api_generate_email():
    """Generate cold email based on sender and receiver profiles."""
    data = request.get_json()
    template = data.get('template') or None
    template_id = data.get('template_id') or None
    template_name = None
    
    # If template_id is provided, load template from database
    if template_id and USER_DATA_ENABLED and user_data_service:
        user_id = session.get('user_id')
        if user_id:
            try:
                template_data = user_data_service.get_template(template_id)
                if template_data and template_data['user_id'] == user_id:
                    template = template_data['content']
                    template_name = template_data['name']
                    # Increment usage count
                    user_data_service.increment_template_usage(template_id)
                else:
                    logger.info("Template %s not found or access denied", template_id)
            except Exception as e:
                logger.warning("Failed to load template %s: %s", template_id, e)
    
    # 是否启用深度搜索（默认启用）
    enable_deep_search = data.get('enable_deep_search', True)
    
    # 获取数据收集 session_id（优先从请求获取，其次从 session）
    session_id = data.get('session_id') or session.get('prompt_session_id')
    
    try:
        # Get sender profile
        sender_data = data.get('sender', {})
        sender = SenderProfile(
            name=sender_data.get('name', ''),
            raw_text=sender_data.get('raw_text', ''),
            education=sender_data.get('education', []),
            experiences=sender_data.get('experiences', []),
            skills=sender_data.get('skills', []),
            projects=sender_data.get('projects', []),
            motivation=sender_data.get('motivation', ''),
            ask=sender_data.get('ask', ''),
        )
        
        # Get receiver profile
        receiver_data = data.get('receiver', {})
        receiver_context = (receiver_data.get('context') or '').strip()

        extra_context_lines = []
        receiver_position = (receiver_data.get('position') or '').strip()
        if receiver_position:
            extra_context_lines.append(f"Current role: {receiver_position}")
        receiver_linkedin = (receiver_data.get('linkedin_url') or '').strip()
        if receiver_linkedin:
            extra_context_lines.append(f"LinkedIn: {receiver_linkedin}")

        evidence = receiver_data.get('evidence')
        if isinstance(evidence, list):
            evidence_lines = [str(e).strip() for e in evidence if isinstance(e, (str, int, float)) and str(e).strip()]
            if evidence_lines:
                extra_context_lines.append("Evidence snippets:")
                extra_context_lines.extend([f"- {e}" for e in evidence_lines[:2]])

        if extra_context_lines:
            extra_context = "\n".join(extra_context_lines)
            receiver_context = f"{receiver_context}\n\n{extra_context}".strip() if receiver_context else extra_context

        sources_value = receiver_data.get('sources', None)
        receiver_sources = None
        if isinstance(sources_value, list):
            receiver_sources = [str(s).strip() for s in sources_value if isinstance(s, str) and s.strip()]
        elif isinstance(sources_value, str) and sources_value.strip():
            receiver_sources = [sources_value.strip()]

        if receiver_linkedin:
            receiver_sources = receiver_sources or []
            if receiver_linkedin not in receiver_sources:
                receiver_sources.append(receiver_linkedin)

        receiver = ReceiverProfile(
            name=receiver_data.get('name', ''),
            raw_text=receiver_data.get('raw_text', ''),
            education=receiver_data.get('education', []),
            experiences=receiver_data.get('experiences', []),
            skills=receiver_data.get('skills', []),
            projects=receiver_data.get('projects', []),
            context=receiver_context or None,
            sources=receiver_sources,
        )
        
        # 深度搜索：在生成邮件前搜索目标人物的更多信息
        deep_search_result = None
        if enable_deep_search and receiver.name:
            try:
                logger.info("Starting deep search for: %s", receiver.name)
                receiver = enrich_receiver_with_deep_search(
                    receiver=receiver,
                    position=receiver_position,
                    linkedin_url=receiver_linkedin,
                )
                deep_search_result = "success"
            except Exception as e:
                logger.warning("Deep search failed (continuing without): %s", e)
                deep_search_result = f"failed: {str(e)}"
        
        # Get goal
        goal = data.get('goal', '')
        if not goal:
            return jsonify({'error': 'Goal is required'}), 400
        
        # Generate email (optionally template-guided)
        email_text = generate_email(sender, receiver, goal, template=template, session_id=session_id)
        
        # 结束数据收集会话并保存
        saved_path = None
        if PROMPT_COLLECTOR_ENABLED and session_id:
            saved_path = end_prompt_session(session_id)
            session.pop('prompt_session_id', None)  # 清理 session
        
        _log_activity_event(
            user_id=session.get('user_id', ''),
            event_type='email_generated',
            activity_id=data.get('activity_id') if isinstance(data, dict) else None,
            payload={
                'goal': goal,
                'template': template,
                'template_id': template_id,
                'template_name': template_name,
                'receiver': {
                    'name': receiver.name,
                    'position': receiver_position,
                    'linkedin_url': receiver_linkedin,
                },
                'deep_search': deep_search_result,
                'email_text': email_text,
            },
        )

        return jsonify({
            'success': True,
            'email': email_text,
            'data_saved': saved_path is not None,
            'deep_search': deep_search_result,
            'template_used': {
                'id': template_id,
                'name': template_name,
            } if template_id and template_name else None,
        })
    
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'has_deep_search': enable_deep_search},
                user_id=session.get('user_id'),
                request_path='/api/generate-email',
            )
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-questionnaire', methods=['POST'])
@login_required
@limiter.limit("12 per hour")
def api_generate_questionnaire():
    """Generate questionnaire questions based on purpose and field."""
    data = request.get_json()
    
    purpose = data.get('purpose', '').strip()
    field = data.get('field', '').strip()
    
    if not purpose or not field:
        return jsonify({'error': 'Purpose and field are required'}), 400
    
    try:
        questions = generate_questionnaire(purpose, field)
        return jsonify({
            'success': True,
            'questions': questions
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/next-question', methods=['POST'])
@login_required
def api_next_question():
    """Generate the next questionnaire question based on history."""
    data = request.get_json()
    
    purpose = (data.get('purpose') or '').strip()
    field = (data.get('field') or '').strip()
    history = data.get('history') or []
    max_questions = data.get('max_questions') or 5
    
    try:
        result = generate_next_question(
            purpose,
            field,
            history,
            max_questions=int(max_questions) if isinstance(max_questions, (int, str)) else 5,
        )
        
        # Log activity
        user_id = session.get('user_id', '')
        if user_id and result:
            _log_activity_event(
                user_id=user_id,
                event_type='questionnaire_question' if not result.get('done') else 'questionnaire_completed',
                activity_id=data.get('activity_id'),
                payload={
                    'purpose': purpose,
                    'field': field,
                    'question_count': len(history),
                    'done': result.get('done', False),
                    'question': result.get('question') if not result.get('done') else None,
                }
            )
        
        return jsonify({
            'success': True,
            **result,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/next-target-question', methods=['POST'])
@login_required
def api_next_target_question():
    """Generate the next preference question for target recommendations."""
    data = request.get_json()
    
    purpose = (data.get('purpose') or '').strip()
    field = (data.get('field') or '').strip()
    sender_profile = data.get('sender_profile') or None
    history = data.get('history') or []
    max_questions = data.get('max_questions') or 5
    
    try:
        result = generate_next_target_question(
            purpose,
            field,
            sender_profile,
            history,
            max_questions=int(max_questions) if isinstance(max_questions, (int, str)) else 5,
        )
        
        # Log activity
        user_id = session.get('user_id', '')
        if user_id and result:
            _log_activity_event(
                user_id=user_id,
                event_type='target_preference_question' if not result.get('done') else 'target_preferences_completed',
                activity_id=data.get('activity_id'),
                payload={
                    'purpose': purpose,
                    'field': field,
                    'question_count': len(history),
                    'done': result.get('done', False),
                    'dimension': result.get('meta', {}).get('dimension') if not result.get('done') else None,
                }
            )
        
        return jsonify({
            'success': True,
            **result,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/profile-from-questionnaire', methods=['POST'])
@login_required
def api_profile_from_questionnaire():
    """Build sender profile from questionnaire answers."""
    data = request.get_json()
    
    purpose = data.get('purpose', '').strip()
    field = data.get('field', '').strip()
    answers = data.get('answers', [])
    
    if not answers:
        return jsonify({'error': 'Answers are required'}), 400
    
    try:
        profile = build_profile_from_answers(purpose, field, answers)
        profile_dict = {
            'name': profile.get('name', 'User'),
            'raw_text': profile.get('summary', ''),
            'education': profile.get('education', []),
            'experiences': profile.get('experiences', []),
            'skills': profile.get('skills', []),
            'projects': profile.get('projects', []),
        }

        # Persist to the logged-in user's profile (for future sessions)
        user_id = session.get("user_id", "")
        if user_id:
            auth_service.update_user_profile(user_id=user_id, sender_profile=profile_dict)
            
            # Log activity
            _log_activity_event(
                user_id=user_id,
                event_type='profile_built_from_questionnaire',
                activity_id=data.get('activity_id'),
                payload={
                    'purpose': purpose,
                    'field': field,
                    'answer_count': len(answers),
                    'profile': profile_dict,
                }
            )

        return jsonify({
            'success': True,
            'profile': profile_dict
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/find-recommendations', methods=['POST'])
@login_required
@limiter.limit("12 per hour")
def api_find_recommendations():
    """Find recommended target contacts based on user profile and goals."""
    data = request.get_json()
    
    try:
        purpose = _validate_input_length(data.get('purpose', ''), 'purpose')
        field = _validate_input_length(data.get('field', ''), 'field')
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    sender_profile = data.get('sender_profile', {})
    preferences = data.get('preferences', {}) or {}
    
    if not purpose or not field:
        return jsonify({'error': 'Purpose and field are required'}), 400

    # Persist latest preferences to user profile (best-effort)
    user_id = session.get("user_id", "")
    if user_id and isinstance(preferences, dict):
        auth_service.update_user_profile(user_id=user_id, preferences=preferences)
    
    # 开始数据收集会话
    session_id = None
    if PROMPT_COLLECTOR_ENABLED:
        session_id = start_prompt_session(user_info={
            "purpose": purpose,
            "field": field,
            "user_id": user_id,
            "user_email": session.get("user_email", ""),
            "sender_name": sender_profile.get("name", ""),
            "sender_profile": sender_profile,  # 完整的 sender 信息
            "preferences": preferences,  # 用户偏好
        })
        # 存储 session_id 供后续 generate_email 使用
        session['prompt_session_id'] = session_id
    
    try:
        recommendations = find_target_recommendations(
            purpose,
            field,
            sender_profile,
            preferences=preferences,
            session_id=session_id,
        )
        
        # ===== 找人成功后立即保存 =====
        saved_path = None
        if PROMPT_COLLECTOR_ENABLED and session_id and recommendations:
            saved_path = save_find_target_results(session_id, recommendations)
        
        _log_activity_event(
            user_id=user_id,
            event_type='recommendations_found',
            activity_id=(data.get('activity_id') if isinstance(data, dict) else None),
            payload={
                'purpose': purpose,
                'field': field,
                'preferences': preferences,
                'recommendations': recommendations,
                'count': len(recommendations) if recommendations else 0,
            },
        )

        return jsonify({
            'success': True,
            'recommendations': recommendations,
            'session_id': session_id,  # 返回给前端，供后续调用
            'data_saved': saved_path is not None,  # 告知前端数据已保存
        })
    except Exception as e:
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={'purpose': purpose, 'field': field},
                user_id=session.get('user_id'),
                request_path='/api/find-recommendations',
            )
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload-receiver-doc', methods=['POST'])
@login_required
def upload_receiver_doc():
    """Upload and parse receiver document (PDF or text)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    filename = uploaded_file.filename.lower()
    name = request.form.get('name', '').strip()
    field = request.form.get('field', '').strip()
    
    try:
        if filename.endswith('.pdf'):
            # Save to temp file and extract profile using existing function
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                uploaded_file.save(tmp.name)
                profile = extract_profile_from_pdf(Path(tmp.name))
                os.unlink(tmp.name)

            _log_activity_event(
                user_id=session.get('user_id', ''),
                event_type='target_doc_upload',
                payload={
                    'filename': uploaded_file.filename,
                    'name': name or profile.name,
                    'field': field,
                    'profile': {
                        'name': profile.name,
                        'education': profile.education,
                        'experiences': profile.experiences,
                        'skills': profile.skills,
                        'projects': profile.projects,
                        'raw_text_length': len(profile.raw_text or ''),
                    },
                },
            )
            
            return jsonify({
                'success': True,
                'profile': {
                    'name': name or profile.name,
                    'field': field,
                    'raw_text': profile.raw_text,
                    'education': profile.education,
                    'experiences': profile.experiences,
                    'skills': profile.skills,
                    'projects': profile.projects,
                    'sources': ['Uploaded document'],
                }
            })
        elif filename.endswith('.txt') or filename.endswith('.md'):
            # Read text content directly
            content = uploaded_file.read().decode('utf-8')
            
            # Use Gemini to parse the text content
            from src.email_agent import parse_text_to_profile
            profile = parse_text_to_profile(content, name, field)

            _log_activity_event(
                user_id=session.get('user_id', ''),
                event_type='target_doc_upload',
                payload={
                    'filename': uploaded_file.filename,
                    'name': name or profile.get('name', ''),
                    'field': field,
                    'profile': profile,
                },
            )
            
            return jsonify({
                'success': True,
                'profile': profile
            })
        else:
            return jsonify({'error': 'Unsupported file type. Please upload PDF, TXT, or MD file.'}), 400
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/regenerate-email', methods=['POST'])
@login_required
def api_regenerate_email():
    """Regenerate email with a different style."""
    data = request.get_json()
    
    original_email = data.get('original_email', '').strip()
    style_instruction = data.get('style_instruction', '').strip()
    sender_data = data.get('sender', {})
    receiver_data = data.get('receiver', {})
    
    if not original_email:
        return jsonify({'error': 'Original email is required'}), 400
    if not style_instruction:
        return jsonify({'error': 'Style instruction is required'}), 400
    
    try:
        new_email = regenerate_email_with_style(
            original_email=original_email,
            style_instruction=style_instruction,
            sender_info=sender_data,
            receiver_info=receiver_data,
        )
        return jsonify({
            'success': True,
            'email': new_email
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== Template Management API ====================

@app.route('/api/templates', methods=['POST'])
@login_required
def api_save_template():
    """Save a new email template."""
    if not USER_DATA_ENABLED or not user_data_service:
        return jsonify({'error': 'User data service not available'}), 503
    
    data = request.get_json()
    user_id = session.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    name = (data.get('name') or '').strip()
    content = (data.get('content') or '').strip()
    description = (data.get('description') or '').strip()
    
    if not name:
        return jsonify({'error': 'Template name is required'}), 400
    if not content:
        return jsonify({'error': 'Template content is required'}), 400
    
    try:
        template_id = user_data_service.save_template(
            user_id=user_id,
            name=name,
            content=content,
            description=description,
        )
        
        _log_activity_event(
            user_id=user_id,
            event_type='template_saved',
            payload={
                'template_id': template_id,
                'name': name,
            },
        )
        
        return jsonify({
            'success': True,
            'template_id': template_id,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/templates', methods=['GET'])
@login_required
def api_get_templates():
    """Get all templates for the current user."""
    if not USER_DATA_ENABLED or not user_data_service:
        return jsonify({'error': 'User data service not available'}), 503
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        templates = user_data_service.get_user_templates(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        
        return jsonify({
            'success': True,
            'templates': templates,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/templates/<template_id>', methods=['GET'])
@login_required
def api_get_template(template_id):
    """Get a specific template."""
    if not USER_DATA_ENABLED or not user_data_service:
        return jsonify({'error': 'User data service not available'}), 503
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        template = user_data_service.get_template(template_id)
        
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        
        # Verify ownership
        if template['user_id'] != user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        return jsonify({
            'success': True,
            'template': template,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/templates/<template_id>', methods=['PUT'])
@login_required
def api_update_template(template_id):
    """Update an existing template."""
    if not USER_DATA_ENABLED or not user_data_service:
        return jsonify({'error': 'User data service not available'}), 503
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    
    try:
        # Verify ownership
        template = user_data_service.get_template(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        if template['user_id'] != user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        # Update template
        name = data.get('name')
        content = data.get('content')
        description = data.get('description')
        
        success = user_data_service.update_template(
            template_id=template_id,
            name=name.strip() if name else None,
            content=content.strip() if content else None,
            description=description.strip() if description else None,
        )
        
        if success:
            _log_activity_event(
                user_id=user_id,
                event_type='template_updated',
                payload={
                    'template_id': template_id,
                    'changes': {
                        'name': name is not None,
                        'content': content is not None,
                        'description': description is not None,
                    },
                },
            )
        
        return jsonify({
            'success': success,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/templates/<template_id>', methods=['DELETE'])
@login_required
def api_delete_template(template_id):
    """Delete a template."""
    if not USER_DATA_ENABLED or not user_data_service:
        return jsonify({'error': 'User data service not available'}), 503
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        # Verify ownership
        template = user_data_service.get_template(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        if template['user_id'] != user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        # Delete template
        success = user_data_service.delete_template(template_id)
        
        if success:
            _log_activity_event(
                user_id=user_id,
                event_type='template_deleted',
                payload={
                    'template_id': template_id,
                    'name': template['name'],
                },
            )
        
        return jsonify({
            'success': success,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/save-targets', methods=['POST'])
@login_required
def api_save_targets():
    """Save user's selected targets for later analysis."""
    if not USER_UPLOAD_ENABLED or not user_upload_storage:
        return jsonify({'success': True, 'message': 'Upload storage disabled'})
    
    data = request.get_json()
    
    session_id = data.get('session_id', 'default')
    targets = data.get('targets', [])
    activity_id = (data.get('activity_id') or '').strip() or None
    
    if not targets:
        return jsonify({'error': 'No targets provided'}), 400
    
    try:
        path = save_user_targets(session_id, targets)
        _log_activity_event(
            user_id=session.get('user_id', ''),
            event_type='targets_saved',
            activity_id=activity_id,
            payload={
                'session_id': session_id,
                'targets': targets,
                'count': len(targets),
            },
        )
        return jsonify({
            'success': True,
            'path': path,
            'count': len(targets)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/activity/start', methods=['POST'])
@login_required
def api_start_activity():
    """Start a new user activity session."""
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip() or None

    activity = _get_or_start_activity(user_id, title=title)
    if not activity:
        return jsonify({'error': 'Activity logging disabled'}), 400

    return jsonify({'success': True, 'activity': activity})


@app.route('/api/activity/event', methods=['POST'])
@login_required
def api_activity_event():
    """Append an event to the current activity session."""
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    activity_id = (data.get('activity_id') or '').strip() or None
    event_type = (data.get('event_type') or '').strip()
    payload = data.get('payload') or {}

    if not event_type:
        return jsonify({'error': 'event_type is required'}), 400

    event = _log_activity_event(
        user_id=user_id,
        event_type=event_type,
        payload=payload,
        activity_id=activity_id,
    )

    if not event:
        return jsonify({'error': 'Activity logging disabled'}), 400

    return jsonify({'success': True, 'event': event, 'activity_id': session.get('activity_id')})


# ==================== User Dashboard & Data APIs ====================

@app.route('/api/user/dashboard', methods=['GET'])
@login_required
def api_user_dashboard():
    """Get user's dashboard data including contacts, emails, and credits."""
    user_id = session.get('user_id')
    try:
        dashboard = user_data_service.get_user_dashboard(user_id)
        return jsonify(dashboard)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/contacts', methods=['GET'])
@login_required
def api_user_contacts():
    """Get user's saved contacts."""
    user_id = session.get('user_id')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    try:
        contacts = user_data_service.get_user_contacts(user_id, limit=limit, offset=offset)
        return jsonify({
            'contacts': [c.to_dict() for c in contacts],
            'count': len(contacts),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/contacts', methods=['POST'])
@login_required
def api_save_contact():
    """Save a contact for the user."""
    user_id = session.get('user_id')
    data = request.get_json()
    activity_id = (data.get('activity_id') or '').strip() if isinstance(data, dict) else None
    
    if not data or not data.get('name'):
        return jsonify({'error': 'Contact name is required'}), 400
    
    try:
        contact = user_data_service.save_contact(user_id, data)
        _log_activity_event(
            user_id=user_id,
            event_type='contact_saved',
            activity_id=activity_id,
            payload={
                'contact': contact.to_dict(),
            },
        )
        return jsonify({
            'success': True,
            'contact': contact.to_dict(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/contacts/<contact_id>', methods=['DELETE'])
@login_required
def api_delete_contact(contact_id):
    """Delete a saved contact."""
    user_id = session.get('user_id')
    
    try:
        success = user_data_service.delete_contact(contact_id, user_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Contact not found or not owned by user'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/emails', methods=['GET'])
@login_required
def api_user_emails():
    """Get user's saved emails."""
    user_id = session.get('user_id')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    try:
        emails = user_data_service.get_user_emails(user_id, limit=limit, offset=offset)
        return jsonify({
            'emails': [e.to_dict() for e in emails],
            'count': len(emails),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/emails', methods=['POST'])
@login_required
def api_save_email():
    """Save a generated email for the user."""
    user_id = session.get('user_id')
    data = request.get_json()
    activity_id = (data.get('activity_id') or '').strip() if isinstance(data, dict) else None
    
    if not data:
        return jsonify({'error': 'Email data is required'}), 400
    
    contact_name = data.get('contact_name', '')
    subject = data.get('subject', '')
    body = data.get('body', '')
    
    if not contact_name or not body:
        return jsonify({'error': 'Contact name and email body are required'}), 400
    
    try:
        email = user_data_service.save_email(
            user_id=user_id,
            contact_name=contact_name,
            contact_position=data.get('contact_position', ''),
            subject=subject,
            body=body,
            goal=data.get('goal', ''),
            contact_id=data.get('contact_id'),
            template_used=data.get('template_used'),
        )
        _log_activity_event(
            user_id=user_id,
            event_type='email_saved',
            activity_id=activity_id,
            payload={
                'email': email.to_dict(),
            },
        )
        return jsonify({
            'success': True,
            'email': email.to_dict(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/emails/<email_id>', methods=['DELETE'])
@login_required
def api_delete_email(email_id):
    """Delete a saved email."""
    user_id = session.get('user_id')
    
    try:
        success = user_data_service.delete_email(email_id, user_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Email not found or not owned by user'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/credits', methods=['GET'])
@login_required
def api_user_credits():
    """Get user's Apollo credits."""
    user_id = session.get('user_id')
    
    try:
        credits = user_data_service.get_user_credits(user_id)
        return jsonify(credits.to_dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== Apollo Email Lookup API ====================

@app.route('/api/apollo/unlock-email', methods=['POST'])
@login_required
def api_apollo_unlock_email():
    """
    Unlock a contact's email using Apollo.io.
    Consumes 1 credit per successful lookup.
    """
    user_id = session.get('user_id')
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Request data is required'}), 400
    
    contact_id = data.get('contact_id')
    name = data.get('name', '')
    linkedin_url = data.get('linkedin_url', '')
    company = data.get('company', '')
    
    if not name and not linkedin_url:
        return jsonify({'error': 'Name or LinkedIn URL is required'}), 400
    
    try:
        # Check user credits first
        credits = user_data_service.get_user_credits(user_id)
        if credits.apollo_credits <= 0:
            return jsonify({
                'success': False,
                'error': 'No credits remaining. You have used all your email lookup credits.',
                'credits_remaining': 0,
            }), 402  # Payment Required
        
        # Look up email using Apollo
        result = lookup_contact_email(
            name=name,
            linkedin_url=linkedin_url,
            company=company,
        )
        
        if result.success and result.email:
            # Deduct credit only on successful lookup
            success, remaining = user_data_service.use_credit(user_id)
            
            # Update contact if we have a contact_id
            if contact_id:
                user_data_service.update_contact_email(contact_id, result.email)
            
            return jsonify({
                'success': True,
                'email': result.email,
                'email_status': result.email_status,
                'credits_remaining': remaining,
                'enriched_data': {
                    'first_name': result.first_name,
                    'last_name': result.last_name,
                    'title': result.title,
                    'organization': result.organization,
                    'city': result.city,
                    'country': result.country,
                },
            })
        else:
            # No credit deducted if lookup fails
            return jsonify({
                'success': False,
                'error': result.error or 'Email not found',
                'credits_remaining': credits.apollo_credits,
            })
    
    except Exception as e:
        # Notify error to WeChat Work
        if ERROR_NOTIFICATION_ENABLED and error_notifier:
            error_notifier.notify_error(
                error=e,
                context={
                    'name': name,
                    'linkedin_url': linkedin_url,
                    'company': company,
                    'contact_id': contact_id,
                },
                user_id=user_id,
                request_path='/api/apollo/unlock-email',
            )
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Make sure GEMINI_API_KEY is set
    if not os.environ.get('GEMINI_API_KEY') and not os.environ.get('GOOGLE_API_KEY'):
        logger.warning("GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

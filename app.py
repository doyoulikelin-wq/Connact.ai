"""Flask web application for Connact.ai."""

import os
import tempfile
from pathlib import Path
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for

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
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'coldemail-secret-key-2024')

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


def login_required(f):
    """Decorator to require login for API endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    """Render the main page."""
    if not session.get('user_id'):
        return redirect(url_for('login'))
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


@app.route('/v3')
def index_v3():
    """Render the v3 interface for testing."""
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return render_template('index_v3.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle login."""
    if request.method == 'GET':
        if session.get('user_id'):
            return redirect(url_for('index'))

        error = request.args.get("error")
        message = request.args.get("message")
        return render_template(
            'login.html',
            google_login_enabled=GOOGLE_LOGIN_ENABLED,
            error=error,
            message=message,
            invite_only=auth_service.invite_only,
            invite_required_for_login=auth_service.invite_required_for_login,
        )
    
    # Handle POST - check for both JSON and form data (email/password login)
    if request.is_json:
        data = request.get_json()
        email = (data.get('email', '') or '').strip()
        password = data.get('password', '')
        invite_code = (data.get("invite_code", "") or "").strip()
    else:
        email = (request.form.get('email', '') or '').strip()
        password = request.form.get('password', '')
        invite_code = (request.form.get("invite_code", "") or "").strip()
    
    try:
        auth_service.validate_invite_for_login(invite_code)
        user = auth_service.authenticate_password(
            email=email,
            password=password,
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        session["user_id"] = user.id
        session["user_email"] = user.primary_email or email
        session["user_name"] = user.display_name or ""
        session["user_picture"] = user.avatar_url or ""
        session["login_method"] = "password"
        session.permanent = True
        if request.is_json:
            return jsonify({"success": True})
        return redirect(url_for("index"))
    except EmailNotVerifiedError:
        if request.is_json:
            return jsonify({"error": "Email not verified", "code": "email_not_verified"}), 403
        return redirect(url_for("login", error="Email not verified. Please verify your email first."))
    except InvalidCredentialsError:
        if request.is_json:
            return jsonify({"error": "Invalid email or password"}), 401
        return redirect(url_for("login", error="Invalid email or password."))
    except AuthError as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 400
        return redirect(url_for("login", error=str(e)))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Invite-only signup for email/password accounts (requires email verification)."""
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("index"))
        error = request.args.get("error")
        message = request.args.get("message")
        return render_template(
            "signup.html",
            google_login_enabled=GOOGLE_LOGIN_ENABLED,
            error=error,
            message=message,
            invite_only=auth_service.invite_only,
            invite_required_for_login=auth_service.invite_required_for_login,
        )

    if request.is_json:
        data = request.get_json()
        email = (data.get("email", "") or "").strip()
        password = data.get("password", "") or ""
        display_name = (data.get("name", "") or "").strip()
        invite_code = (data.get("invite_code", "") or "").strip()
    else:
        email = (request.form.get("email", "") or "").strip()
        password = request.form.get("password", "") or ""
        display_name = (request.form.get("name", "") or "").strip()
        invite_code = (request.form.get("invite_code", "") or "").strip()

    try:
        verification = auth_service.create_password_user(
            email=email,
            password=password,
            display_name=display_name or None,
            invite_code=invite_code or None,
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

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
        )
    except (InviteRequiredError, InviteInvalidError, SignupDisabledError) as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 403
        return redirect(url_for("signup", error=str(e)))
    except AuthError as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 400
        return redirect(url_for("signup", error=str(e)))


@app.route("/verify-email")
def verify_email():
    """Verify email for password accounts."""
    token = request.args.get("token", "")
    user_id = auth_service.verify_email_token(token)
    if user_id:
        return redirect(url_for("login", message="Email verified. You can now log in."))
    return redirect(url_for("login", error="Invalid or expired verification link."))


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
        return render_template(
            "signup_done.html",
            message=message,
            email=verification.email,
            email_sent=email_sent,
            verification_link=None if email_sent else verification_link,
        )
    except AuthError as e:
        if request.is_json:
            return jsonify({"error": str(e)}), 400
        return redirect(url_for("login", error=str(e)))


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

        invite_code = session.pop("pending_invite_code", None)
        try:
            auth_service.validate_invite_for_login(invite_code)
        except AuthError as e:
            return redirect(url_for("login", error=str(e)))
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

        session["user_id"] = user.id
        session["user_email"] = user.primary_email or (email or "")
        session["user_name"] = user.display_name or (name or "")
        session["user_picture"] = user.avatar_url or (picture or "")
        session["login_method"] = "google"
        session.permanent = True
        return redirect(url_for("index"))
    except Exception as e:
        print(f"Google OAuth error: {e}")
        if isinstance(e, (InviteRequiredError, InviteInvalidError, SignupDisabledError)):
            return redirect(url_for("login", error=str(e)))
    
    return redirect(url_for('login'))


@app.route('/logout')
def logout():
    """Handle logout."""
    session.pop("user_id", None)
    session.pop('user_email', None)
    session.pop('user_name', None)
    session.pop('user_picture', None)
    session.pop('login_method', None)
    return redirect(url_for('index'))


@app.route("/login/google")
def google_login_start():
    """Start Google OAuth flow (stores optional invite code in session for new users)."""
    if not GOOGLE_LOGIN_ENABLED:
        return redirect(url_for("login"))
    invite_code = (request.args.get("invite_code", "") or "").strip()
    if auth_service.invite_required_for_login and not invite_code:
        return redirect(url_for("login", error="Invite code is required."))
    if invite_code:
        session["pending_invite_code"] = invite_code
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


def _send_verification_email(to_email: str, verification_link: str) -> bool:
    """Send email verification link via SMTP if configured.

    Configure with:
      SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        print(f"[verify-email] {to_email}: {verification_link}")
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
        return jsonify({'error': str(e)}), 500


@app.route('/api/search-receiver', methods=['POST'])
@login_required
def search_receiver():
    """Search for receiver information from the web."""
    data = request.get_json()
    
    name = data.get('name', '').strip()
    field = data.get('field', '').strip()
    
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
def api_generate_email():
    """Generate cold email based on sender and receiver profiles."""
    data = request.get_json()
    template = data.get('template') or None
    
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
                print(f"[API] Starting deep search for: {receiver.name}")
                receiver = enrich_receiver_with_deep_search(
                    receiver=receiver,
                    position=receiver_position,
                    linkedin_url=receiver_linkedin,
                )
                deep_search_result = "success"
            except Exception as e:
                print(f"[API] Deep search failed (continuing without): {e}")
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
        
        return jsonify({
            'success': True,
            'email': email_text,
            'data_saved': saved_path is not None,
            'deep_search': deep_search_result,
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/generate-questionnaire', methods=['POST'])
@login_required
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

        return jsonify({
            'success': True,
            'profile': profile_dict
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/find-recommendations', methods=['POST'])
@login_required
def api_find_recommendations():
    """Find recommended target contacts based on user profile and goals."""
    data = request.get_json()
    
    purpose = data.get('purpose', '').strip()
    field = data.get('field', '').strip()
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
        
        return jsonify({
            'success': True,
            'recommendations': recommendations,
            'session_id': session_id,  # 返回给前端，供后续调用
            'data_saved': saved_path is not None,  # 告知前端数据已保存
        })
    except Exception as e:
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


@app.route('/api/save-targets', methods=['POST'])
@login_required
def api_save_targets():
    """Save user's selected targets for later analysis."""
    if not USER_UPLOAD_ENABLED or not user_upload_storage:
        return jsonify({'success': True, 'message': 'Upload storage disabled'})
    
    data = request.get_json()
    
    session_id = data.get('session_id', 'default')
    targets = data.get('targets', [])
    
    if not targets:
        return jsonify({'error': 'No targets provided'}), 400
    
    try:
        path = save_user_targets(session_id, targets)
        return jsonify({
            'success': True,
            'path': path,
            'count': len(targets)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Make sure GEMINI_API_KEY is set
    if not os.environ.get('GEMINI_API_KEY') and not os.environ.get('GOOGLE_API_KEY'):
        print("Warning: GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

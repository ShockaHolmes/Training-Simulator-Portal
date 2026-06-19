from datetime import datetime
from pathlib import Path
import re
import shutil
import zipfile
from functools import wraps

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request,
    send_from_directory, session, url_for
)
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from .models import AuditLog, Completion, ForumPost, ForumTopic, Training, User, db, utcnow
from .security import (
    allowed_training_upload, encrypt_text, make_csrf_token, safe_extract_zip,
    safe_filename, stable_email_hash, verify_csrf_token
)

main_bp = Blueprint("main", __name__)


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value or "training"


def unique_slug(title: str) -> str:
    base = slugify(title)
    slug = base
    counter = 2
    while Training.query.filter_by(slug=slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


@main_bp.app_context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "csrf_token": lambda: make_csrf_token(session),
        "site_name": current_app.config.get("SITE_NAME", "Training Simulator Portal"),
    }


@main_bp.before_app_request
def csrf_protect():
    if request.method == "POST":
        submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not verify_csrf_token(session, submitted):
            abort(400, description="Invalid or missing CSRF token.")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please sign in first.", "warning")
            return redirect(url_for("main.signin", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def access_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please sign in first.", "warning")
            return redirect(url_for("main.signin", next=request.path))
        if not user.has_training_access:
            flash("Your account is pending access. Complete payment, then wait for admin approval.", "warning")
            return redirect(url_for("main.subscribe"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def log_action(action, target=None, details=None):
    actor = current_user()
    db.session.add(AuditLog(actor_id=actor.id if actor else None, action=action, target=target, details=details))


@main_bp.route("/")
def home():
    trainings = Training.query.filter_by(is_published=True).order_by(Training.created_at.desc()).limit(6).all()
    return render_template("home.html", trainings=trainings)


@main_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not username or not name or not email or len(password) < 8:
            flash("Enter a username, name, email, and a password of at least 8 characters.", "danger")
            return render_template("signup.html")
        if User.query.filter_by(username=username).first():
            flash("That username is already taken.", "danger")
            return render_template("signup.html")
        email_hash = stable_email_hash(email)
        if User.query.filter_by(email_hash=email_hash).first():
            flash("An account with that email already exists.", "danger")
            return render_template("signup.html")
        user = User(
            username=username,
            name_enc=encrypt_text(name),
            email_enc=encrypt_text(email),
            email_hash=email_hash,
            role="client",
            subscription_status="active" if current_app.config.get("AUTO_ACTIVATE_DEMO") else "pending",
        )
        user.set_password(password)
        db.session.add(user)
        log_action("client_signup", username, "New client signup")
        db.session.commit()
        session["user_id"] = user.id
        flash("Account created. Complete payment or wait for admin approval to unlock training access.", "success")
        return redirect(url_for("main.subscribe"))
    return render_template("signup.html")


@main_bp.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("Invalid username or password.", "danger")
            return render_template("signin.html")
        if not user.is_enabled:
            flash("This account is disabled. Contact the administrator.", "danger")
            return render_template("signin.html")
        session.clear()
        session["user_id"] = user.id
        user.last_login_at = utcnow()
        log_action("signin", user.username, "User signed in")
        db.session.commit()
        if user.is_admin and user.must_change_password:
            flash("Default admin password is still active. Change it now before going live.", "warning")
            return redirect(url_for("main.admin_settings"))
        next_url = request.args.get("next") or url_for("main.dashboard")
        return redirect(next_url)
    return render_template("signin.html")


@main_bp.route("/logout")
def logout():
    session.clear()
    flash("Signed out.", "info")
    return redirect(url_for("main.home"))


@main_bp.route("/subscribe", methods=["GET", "POST"])
@login_required
def subscribe():
    user = current_user()
    if request.method == "POST":
        log_action("access_request", user.username, "Client requested access review")
        db.session.commit()
        flash("Access request sent. After payment, the admin can activate your account.", "success")
    return render_template("subscribe.html", payment_link=current_app.config.get("PAYMENT_LINK", ""))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if user.is_admin:
        return redirect(url_for("main.admin_dashboard"))
    if not user.has_training_access:
        return redirect(url_for("main.subscribe"))
    trainings = Training.query.filter_by(is_published=True).order_by(Training.created_at.desc()).all()
    completed_ids = {c.training_id: c for c in user.completions}
    return render_template("dashboard.html", trainings=trainings, completed_ids=completed_ids)


@main_bp.route("/training/<int:training_id>")
@access_required
def training_detail(training_id):
    training = db.session.get(Training, training_id) or abort(404)
    if not training.is_published and not current_user().is_admin:
        abort(404)
    completion = Completion.query.filter_by(user_id=current_user().id, training_id=training.id).first()
    return render_template("training_detail.html", training=training, completion=completion)


@main_bp.route("/training/<int:training_id>/complete", methods=["POST"])
@access_required
def complete_training(training_id):
    training = db.session.get(Training, training_id) or abort(404)
    user = current_user()
    completion = Completion.query.filter_by(user_id=user.id, training_id=training.id).first()
    if not completion:
        completion = Completion(user_id=user.id, training_id=training.id)
        db.session.add(completion)
        log_action("complete_training", training.title, f"{user.username} completed {training.title}")
        db.session.commit()
        flash("Training marked complete. Your certificate is ready.", "success")
    return redirect(url_for("main.certificate", certificate_id=completion.certificate_id))


@main_bp.route("/certificate/<certificate_id>")
@login_required
def certificate(certificate_id):
    completion = Completion.query.filter_by(certificate_id=certificate_id).first_or_404()
    user = current_user()
    if not user.is_admin and completion.user_id != user.id:
        abort(403)
    return render_template("certificate.html", completion=completion, issued_date=completion.completed_at.strftime("%B %d, %Y"))


@main_bp.route("/training-content/<int:training_id>/<path:filename>")
@access_required
def training_content(training_id, filename):
    training = db.session.get(Training, training_id) or abort(404)
    root = Path(current_app.instance_path) / "simulators" / training.content_folder
    return send_from_directory(root, filename)


@main_bp.route("/forum")
@access_required
def forum():
    q = request.args.get("q", "").strip()
    query = ForumTopic.query
    if q:
        query = query.filter(or_(ForumTopic.title.ilike(f"%{q}%"), ForumTopic.body.ilike(f"%{q}%")))
    topics = query.order_by(ForumTopic.is_pinned.desc(), ForumTopic.created_at.desc()).all()
    return render_template("forum.html", topics=topics, q=q)


@main_bp.route("/forum/new", methods=["GET", "POST"])
@access_required
def new_topic():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if not title or not body:
            flash("Topic title and message are required.", "danger")
            return render_template("new_topic.html")
        topic = ForumTopic(title=title, body=body, user_id=current_user().id)
        db.session.add(topic)
        log_action("forum_topic_created", title, current_user().username)
        db.session.commit()
        return redirect(url_for("main.topic_detail", topic_id=topic.id))
    return render_template("new_topic.html")


@main_bp.route("/forum/<int:topic_id>", methods=["GET", "POST"])
@access_required
def topic_detail(topic_id):
    topic = db.session.get(ForumTopic, topic_id) or abort(404)
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if not body:
            flash("Reply cannot be empty.", "danger")
        else:
            post = ForumPost(topic_id=topic.id, user_id=current_user().id, body=body)
            db.session.add(post)
            log_action("forum_reply_created", topic.title, current_user().username)
            db.session.commit()
            return redirect(url_for("main.topic_detail", topic_id=topic.id))
    return render_template("topic_detail.html", topic=topic)


@main_bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user = current_user()
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        if name:
            user.name_enc = encrypt_text(name)
        if email:
            new_hash = stable_email_hash(email)
            existing = User.query.filter(User.email_hash == new_hash, User.id != user.id).first()
            if existing:
                flash("Email is already used by another account.", "danger")
                return render_template("account.html")
            user.email_enc = encrypt_text(email)
            user.email_hash = new_hash
        if new_password:
            if not user.check_password(current_password):
                flash("Current password is incorrect.", "danger")
                return render_template("account.html")
            if len(new_password) < 10:
                flash("Use at least 10 characters for the new password.", "danger")
                return render_template("account.html")
            user.set_password(new_password)
            user.must_change_password = False
        log_action("account_updated", user.username, "User updated account")
        db.session.commit()
        flash("Account updated.", "success")
        return redirect(url_for("main.account"))
    return render_template("account.html")


@main_bp.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    trainings = Training.query.order_by(Training.created_at.desc()).all()
    pending_users = User.query.filter_by(role="client", subscription_status="pending").order_by(User.created_at.desc()).all()
    client_count = User.query.filter_by(role="client").count()
    completion_count = Completion.query.count()
    return render_template("admin/dashboard.html", trainings=trainings, pending_users=pending_users, client_count=client_count, completion_count=completion_count)


@main_bp.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)


@main_bp.route("/admin/users/<int:user_id>/update", methods=["POST"])
@login_required
@admin_required
def admin_update_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.username == "ADMIN" and request.form.get("role") != "admin":
        flash("The bootstrap admin cannot be demoted from this form.", "danger")
        return redirect(url_for("main.admin_users"))
    user.subscription_status = request.form.get("subscription_status", user.subscription_status)
    user.is_enabled = request.form.get("is_enabled") == "on"
    log_action("admin_update_user", user.username, f"status={user.subscription_status}, enabled={user.is_enabled}")
    db.session.commit()
    flash("Client access updated.", "success")
    return redirect(url_for("main.admin_users"))


@main_bp.route("/admin/trainings/upload", methods=["GET", "POST"])
@login_required
@admin_required
def admin_upload_training():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        level = request.form.get("level", "").strip()
        upload = request.files.get("training_file")
        if not title or not upload or upload.filename == "":
            flash("Title and upload file are required.", "danger")
            return render_template("admin/upload_training.html")
        if not allowed_training_upload(upload.filename):
            flash("Upload must be an .html, .htm, or .zip file.", "danger")
            return render_template("admin/upload_training.html")

        slug = unique_slug(title)
        training = Training(
            title=title,
            slug=slug,
            description=description,
            category=category,
            level=level,
            content_type="zip" if upload.filename.lower().endswith(".zip") else "html",
            content_folder=slug,
            launch_file="index.html",
            created_by=current_user().id,
            is_published=request.form.get("is_published") == "on",
        )
        db.session.add(training)
        db.session.flush()

        destination = Path(current_app.instance_path) / "simulators" / slug
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)

        filename = safe_filename(upload.filename)
        suffix = Path(filename).suffix.lower()
        try:
            if suffix == ".zip":
                temp_path = Path(current_app.instance_path) / "uploads" / filename
                upload.save(temp_path)
                with zipfile.ZipFile(temp_path) as zf:
                    safe_extract_zip(zf, destination)
                temp_path.unlink(missing_ok=True)
                if not (destination / "index.html").exists():
                    raise ValueError("ZIP simulator must include an index.html file at the top level.")
                training.launch_file = "index.html"
            else:
                upload.save(destination / "index.html")
                training.launch_file = "index.html"
            log_action("training_uploaded", title, f"folder={slug}")
            db.session.commit()
            flash("Training simulator uploaded successfully.", "success")
            return redirect(url_for("main.admin_dashboard"))
        except Exception as exc:
            db.session.rollback()
            if destination.exists():
                shutil.rmtree(destination)
            flash(f"Upload failed: {exc}", "danger")
            return render_template("admin/upload_training.html")
    return render_template("admin/upload_training.html")


@main_bp.route("/admin/trainings/<int:training_id>/toggle", methods=["POST"])
@login_required
@admin_required
def admin_toggle_training(training_id):
    training = db.session.get(Training, training_id) or abort(404)
    training.is_published = not training.is_published
    log_action("training_publish_toggle", training.title, f"published={training.is_published}")
    db.session.commit()
    flash("Training visibility updated.", "success")
    return redirect(url_for("main.admin_dashboard"))


@main_bp.route("/admin/trainings/<int:training_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_training(training_id):
    training = db.session.get(Training, training_id) or abort(404)
    folder = Path(current_app.instance_path) / "simulators" / training.content_folder
    title = training.title
    db.session.delete(training)
    log_action("training_deleted", title, f"folder={training.content_folder}")
    db.session.commit()
    if folder.exists():
        shutil.rmtree(folder)
    flash("Training simulator removed.", "success")
    return redirect(url_for("main.admin_dashboard"))


@main_bp.route("/admin/forum/<int:topic_id>/pin", methods=["POST"])
@login_required
@admin_required
def admin_pin_topic(topic_id):
    topic = db.session.get(ForumTopic, topic_id) or abort(404)
    topic.is_pinned = not topic.is_pinned
    db.session.commit()
    return redirect(url_for("main.topic_detail", topic_id=topic.id))


@main_bp.route("/admin/settings", methods=["GET", "POST"])
@login_required
@admin_required
def admin_settings():
    user = current_user()
    if request.method == "POST":
        new_username = request.form.get("username", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        if new_username and new_username != user.username:
            if User.query.filter_by(username=new_username).first():
                flash("Username is already taken.", "danger")
                return render_template("admin/settings.html")
            user.username = new_username
        if new_password:
            if not user.check_password(current_password):
                flash("Current password is incorrect.", "danger")
                return render_template("admin/settings.html")
            if len(new_password) < 12:
                flash("Admin password must be at least 12 characters.", "danger")
                return render_template("admin/settings.html")
            user.set_password(new_password)
            user.must_change_password = False
        log_action("admin_settings_updated", user.username, "Admin credentials/settings changed")
        db.session.commit()
        flash("Admin settings updated.", "success")
        return redirect(url_for("main.admin_settings"))
    return render_template("admin/settings.html")


@main_bp.route("/admin/audit")
@login_required
@admin_required
def admin_audit():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return render_template("admin/audit.html", logs=logs)


@main_bp.app_template_filter("dt")
def format_dt(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y %I:%M %p")
    return value

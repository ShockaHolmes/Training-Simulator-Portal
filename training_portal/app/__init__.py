import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from flask import Flask
from .models import db, User, Training, AuditLog
from .security import encrypt_text, stable_email_hash, get_secret_key


def create_app(test_config=None):
    base_dir = Path(__file__).resolve().parent.parent
    instance_dir = base_dir / "instance"
    instance_dir.mkdir(exist_ok=True)
    (instance_dir / "uploads").mkdir(exist_ok=True)
    (instance_dir / "simulators").mkdir(exist_ok=True)

    app = Flask(__name__, instance_path=str(instance_dir), instance_relative_config=True)
    app.config.update(
        SECRET_KEY=get_secret_key(),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL") or f"sqlite:///{instance_dir / 'training_portal.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=int(os.environ.get("MAX_CONTENT_MB", "75")) * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true",
        REMEMBER_COOKIE_SECURE=True,
        PAYMENT_LINK=os.environ.get("PAYMENT_LINK", ""),
        SITE_NAME=os.environ.get("SITE_NAME", "Training Simulator Portal"),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    from .routes import main_bp
    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()
        bootstrap_admin()
        bootstrap_demo_training()

    return app


def bootstrap_admin():
    admin = User.query.filter_by(username="ADMIN").first()
    if not admin:
        admin = User(
            username="ADMIN",
            name_enc=encrypt_text("Administrator"),
            email_enc=encrypt_text("admin@example.local"),
            email_hash=stable_email_hash("admin@example.local"),
            role="admin",
            subscription_status="active",
            must_change_password=True,
        )
        admin.set_password("admin1")
        db.session.add(admin)
        db.session.add(AuditLog(action="bootstrap_admin", target="ADMIN", details="Default admin created. Change password immediately."))
        db.session.commit()


def bootstrap_demo_training():
    # A small built-in simulator proves the portal works before the admin uploads real simulator files.
    existing = Training.query.filter_by(slug="welcome-simulator").first()
    if existing:
        return
    base_dir = Path(__file__).resolve().parent.parent
    demo_folder = base_dir / "instance" / "simulators" / "welcome-simulator"
    demo_folder.mkdir(parents=True, exist_ok=True)
    (demo_folder / "index.html").write_text("""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Welcome Training Simulator</title>
<style>
body{font-family:Arial,sans-serif;background:#101827;color:#fff;margin:0;padding:32px;line-height:1.6}
.card{max-width:850px;margin:auto;background:linear-gradient(135deg,#1d2b50,#172036);border:1px solid rgba(255,255,255,.16);border-radius:24px;padding:32px;box-shadow:0 24px 80px rgba(0,0,0,.35)}
button{background:#73e2ff;color:#0b1020;border:0;border-radius:999px;padding:12px 22px;font-weight:800;cursor:pointer} .step{display:none}.step.active{display:block}.badge{display:inline-block;padding:6px 12px;border-radius:999px;background:rgba(115,226,255,.16);color:#99ecff}
</style>
</head>
<body><main class='card'>
<span class='badge'>Demo Simulator</span>
<h1>Welcome to Your Training Portal</h1>
<div class='step active'><h2>Lesson 1: Start</h2><p>This is a sample simulator. Upload your own HTML or ZIP simulator from the admin panel.</p></div>
<div class='step'><h2>Lesson 2: Practice</h2><p>Training simulators can include quizzes, code editors, games, videos, or interactive lessons.</p></div>
<div class='step'><h2>Lesson 3: Complete</h2><p>Return to the portal and click <strong>Mark Complete</strong> to generate a certificate.</p></div>
<button onclick='nextStep()'>Next Step</button>
</main><script>
let i=0;const steps=[...document.querySelectorAll('.step')];function nextStep(){steps[i].classList.remove('active');i=(i+1)%steps.length;steps[i].classList.add('active')}
</script></body></html>""", encoding="utf-8")
    training = Training(
        title="Welcome Training Simulator",
        slug="welcome-simulator",
        description="A sample simulator showing how uploaded lessons launch inside the secure portal.",
        category="Getting Started",
        level="Beginner",
        content_type="html",
        content_folder="welcome-simulator",
        launch_file="index.html",
        is_published=True,
    )
    db.session.add(training)
    db.session.commit()

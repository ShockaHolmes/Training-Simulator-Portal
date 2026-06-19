from datetime import datetime, timezone
import uuid
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from .security import decrypt_text


db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name_enc = db.Column(db.Text, nullable=False)
    email_enc = db.Column(db.Text, nullable=False)
    email_hash = db.Column(db.String(128), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="client")
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    subscription_status = db.Column(db.String(20), nullable=False, default="pending")
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    completions = db.relationship("Completion", backref="user", lazy=True)
    topics = db.relationship("ForumTopic", backref="author", lazy=True)
    posts = db.relationship("ForumPost", backref="author", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def display_name(self) -> str:
        return decrypt_text(self.name_enc)

    @property
    def email(self) -> str:
        return decrypt_text(self.email_enc)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def has_training_access(self) -> bool:
        return self.is_enabled and (self.is_admin or self.subscription_status == "active")


class Training(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), nullable=False, unique=True, index=True)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(80), nullable=True)
    level = db.Column(db.String(40), nullable=True)
    content_type = db.Column(db.String(20), nullable=False)
    content_folder = db.Column(db.String(255), nullable=False)
    launch_file = db.Column(db.String(255), nullable=False, default="index.html")
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    completions = db.relationship("Completion", backref="training", cascade="all, delete-orphan", lazy=True)


class Completion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    training_id = db.Column(db.Integer, db.ForeignKey("training.id"), nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    certificate_id = db.Column(db.String(64), unique=True, nullable=False, default=lambda: uuid.uuid4().hex)
    __table_args__ = (db.UniqueConstraint("user_id", "training_id", name="unique_user_training_completion"),)


class ForumTopic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    posts = db.relationship("ForumPost", backref="topic", cascade="all, delete-orphan", lazy=True)


class ForumPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("forum_topic.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    action = db.Column(db.String(120), nullable=False)
    target = db.Column(db.String(160), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

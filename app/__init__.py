import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from celery import Celery

from config import config

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
bcrypt = Bcrypt()
celery_app = Celery()


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    bcrypt.init_app(app)
    allowed_origins = app.config.get(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    CORS(
        app,
        resources={r"/api/*": {"origins": allowed_origins}},
        supports_credentials=True,
    )

    # Celery
    celery_app.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
    )

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.customer import customer_bp
    from app.routes.rider import rider_bp
    from app.routes.shop import shop_bp
    from app.routes.notifications import notifications_bp
    from app.routes.upload import upload_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(customer_bp, url_prefix="/api/customer")
    app.register_blueprint(rider_bp, url_prefix="/api/rider")
    app.register_blueprint(shop_bp, url_prefix="/api/shop")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(upload_bp, url_prefix="/api/uploads")

    # Auto-create database + tables + seed data (skipped in testing)
    if not app.config.get("TESTING"):
        try:
            from app.init_db import ensure_database_exists, init_db
            ensure_database_exists(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
            init_db(app, db)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("DB init error: %s", exc)

    # JWT error handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return {"error": "Token has expired", "success": False}, 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return {"error": "Invalid token", "success": False}, 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return {"error": "Authorization token required", "success": False}, 401

    # Health check
    @app.route("/api/health")
    def health():
        return {"status": "ok", "success": True}

    return app

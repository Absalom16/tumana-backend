from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)
from app import db
from app.models.user import User
from app.models.wallet import Wallet
from app.utils.helpers import success_response, error_response, get_current_user
from app.utils.otp_service import OTPService

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    identifier = data.get("identifier")  # phone or email
    password = data.get("password")

    if not identifier or not password:
        return error_response("Identifier and password are required")

    user = User.query.filter(
        (User.phone == identifier) | (User.email == identifier)
    ).first()

    if not user or not user.check_password(password):
        return error_response("Invalid credentials", 401)

    if user.status == "suspended":
        return error_response("Account has been suspended", 403)

    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return success_response(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user.to_dict(),
        },
        message="Login successful",
    )


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    required = ["role", "name", "phone", "password"]
    for field in required:
        if not data.get(field):
            return error_response(f"'{field}' is required")

    if User.query.filter_by(phone=data["phone"]).first():
        return error_response("Phone number already registered")

    if data.get("email") and User.query.filter_by(email=data["email"]).first():
        return error_response("Email already registered")

    user = User(
        name=data["name"],
        phone=data["phone"],
        email=data.get("email"),
        role=data["role"],
        id_number=data.get("id_number"),
        status="pending",
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.flush()

    # Create wallet
    wallet = Wallet(user_id=user.id)
    db.session.add(wallet)

    # Send OTP
    OTPService.send_otp(data["phone"])

    db.session.commit()

    return success_response(
        data={
            "message": "Registration successful. Please verify your phone.",
            "requires_verification": True,
            "user_id": user.id,
        },
        message="Registration successful",
        status_code=201,
    )


@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    phone = data.get("phone")
    otp_code = data.get("otp_code")

    if not phone or not otp_code:
        return error_response("Phone and OTP code are required")

    if not OTPService.verify_otp(phone, otp_code):
        return error_response("Invalid or expired OTP", 401)

    user = User.query.filter_by(phone=phone).first()
    if not user:
        return error_response("User not found", 404)

    user.is_verified = True
    user.status = "active"
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return success_response(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user.to_dict(),
        },
        message="OTP verified successfully",
    )


@auth_bp.route("/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json()
    phone = data.get("phone")

    if not phone:
        return error_response("Phone number is required")

    success = OTPService.send_otp(phone)
    if not success:
        return error_response("Failed to send OTP. Please try again.", 500)

    return success_response(
        data={"otp_id": phone},
        message="OTP sent successfully",
    )


@auth_bp.route("/register-otp", methods=["POST"])
def register_with_otp():
    data = request.get_json()
    phone = data.get("phone")
    otp = data.get("otp")

    if not OTPService.verify_otp(phone, otp):
        return error_response("Invalid or expired OTP", 401)

    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(
            name=data.get("name", ""),
            phone=phone,
            email=data.get("email"),
            role=data.get("role", "customer"),
            status="active",
            is_verified=True,
        )
        db.session.add(user)
        db.session.flush()
        wallet = Wallet(user_id=user.id)
        db.session.add(wallet)
    else:
        user.is_verified = True
        user.status = "active"

    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return success_response(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user.to_dict(),
        },
    )


@auth_bp.route("/fingerprint-register", methods=["POST"])
def fingerprint_register():
    data = request.get_json()
    phone = data.get("phone")
    fingerprint_template = data.get("fingerprint_template")

    user = User.query.filter_by(phone=phone).first()
    if not user:
        return error_response("User not found", 404)

    user.fingerprint_template = fingerprint_template
    db.session.commit()

    return success_response(
        data={"fingerprint_id": str(user.id)},
        message="Fingerprint registered successfully",
    )


@auth_bp.route("/fingerprint-login", methods=["POST"])
def fingerprint_login():
    data = request.get_json()
    phone = data.get("phone")
    fingerprint_template = data.get("fingerprint_template")

    user = User.query.filter_by(phone=phone).first()
    if not user or not user.fingerprint_template:
        return error_response("Fingerprint not registered", 401)

    # In production, use a proper fingerprint matching library
    if user.fingerprint_template != fingerprint_template:
        return error_response("Fingerprint mismatch", 401)

    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return success_response(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user.to_dict(),
        },
    )


@auth_bp.route("/pin-login", methods=["POST"])
def pin_login():
    data = request.get_json()
    phone = data.get("phone")
    pin = data.get("pin")

    user = User.query.filter_by(phone=phone).first()
    if not user:
        return error_response("User not found", 404)

    if not user.check_pin(pin):
        return error_response("Invalid PIN", 401)

    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return success_response(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user.to_dict(),
        },
    )


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    access_token = create_access_token(identity=str(user_id))
    refresh_token = create_refresh_token(identity=str(user_id))
    return success_response(data={"access_token": access_token, "refresh_token": refresh_token})


@auth_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    user = get_current_user()
    if not user:
        return error_response("User not found", 404)
    return success_response(data=user.to_dict())


@auth_bp.route("/set-pin", methods=["POST"])
@jwt_required()
def set_pin():
    user = get_current_user()
    if not user:
        return error_response("User not found", 404)
    data = request.get_json()
    pin = data.get("pin")
    if not pin or len(str(pin)) < 4:
        return error_response("PIN must be at least 4 digits")
    user.set_pin(str(pin))
    db.session.commit()
    return success_response(message="PIN set successfully")


@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    user = get_current_user()
    if not user:
        return error_response("User not found", 404)
    data = request.get_json()
    current_password = data.get("current_password")
    new_password = data.get("new_password")
    if not current_password or not new_password:
        return error_response("Current and new passwords are required")
    if not user.check_password(current_password):
        return error_response("Current password is incorrect", 401)
    user.set_password(new_password)
    db.session.commit()
    return success_response(message="Password changed successfully")

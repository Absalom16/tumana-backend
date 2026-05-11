import random
import string
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app import db
from app.models.user import User


def generate_order_number():
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"ORD-{suffix}"


def generate_otp(length=6):
    return "".join(random.choices(string.digits, k=length))


def paginate_query(query, page=1, per_page=10):
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "items": paginated.items,
        "pagination": {
            "currentPage": paginated.page,
            "totalPages": paginated.pages,
            "totalItems": paginated.total,
            "perPage": per_page,
        },
    }


def success_response(data=None, message="Success", status_code=200):
    resp = {"success": True, "message": message}
    if data is not None:
        resp["data"] = data
    return jsonify(resp), status_code


def error_response(message="An error occurred", status_code=400, errors=None):
    resp = {"success": False, "error": message}
    if errors:
        resp["errors"] = errors
    return jsonify(resp), status_code


def require_role(*roles):
    """Decorator to restrict access to specific roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user = User.query.get(int(user_id))
            if not user or user.role not in roles:
                return error_response("Unauthorized: insufficient permissions", 403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_current_user():
    user_id = get_jwt_identity()
    return User.query.get(int(user_id))


def update_shop_rating(shop):
    """Recalculate and update shop rating from reviews."""
    from app.models.shop import Review
    reviews = Review.query.filter_by(shop_id=shop.id).all()
    if reviews:
        shop.rating = sum(r.rating for r in reviews) / len(reviews)
        shop.total_reviews = len(reviews)
        db.session.commit()

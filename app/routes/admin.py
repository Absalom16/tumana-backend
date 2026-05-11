from datetime import datetime, timedelta
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func, desc
from app import db
from app.models.user import User
from app.models.shop import Shop, ShopCategory
from app.models.order import Order, OrderItem
from app.models.wallet import Wallet, WalletTransaction
from app.models.subscription import Subscription
from app.models.notification import Notification
from app.models.payout import Payout
from app.utils.helpers import (
    success_response, error_response, require_role,
    get_current_user, paginate_query,
)

admin_bp = Blueprint("admin", __name__)


# ──────────────────────────────────────────────
# ANALYTICS
# ──────────────────────────────────────────────

@admin_bp.route("/analytics", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_analytics():
    time_range = request.args.get("timeRange", "7days")
    days_map = {"7days": 7, "30days": 30, "90days": 90, "1year": 365}
    days = days_map.get(time_range, 7)
    since = datetime.utcnow() - timedelta(days=days)

    total_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status == "delivered", Order.created_at >= since
    ).scalar() or 0

    total_orders = Order.query.filter(Order.created_at >= since).count()
    total_users = User.query.filter(User.created_at >= since).count()
    active_users = User.query.filter(User.last_login >= since).count()
    avg_order_value = total_revenue / total_orders if total_orders else 0

    # Time series
    time_series = []
    for i in range(days):
        day = since + timedelta(days=i)
        day_end = day + timedelta(days=1)
        rev = db.session.query(func.sum(Order.total_amount)).filter(
            Order.status == "delivered",
            Order.created_at >= day,
            Order.created_at < day_end,
        ).scalar() or 0
        ords = Order.query.filter(Order.created_at >= day, Order.created_at < day_end).count()
        time_series.append({
            "date": day.strftime("%b %d"),
            "fullDate": day.isoformat(),
            "revenue": rev,
            "orders": ords,
        })

    return success_response(
        data={
            "timeSeriesData": time_series,
            "summary": {
                "totalRevenue": total_revenue,
                "totalOrders": total_orders,
                "totalUsers": total_users,
                "activeUsers": active_users,
                "avgOrderValue": avg_order_value,
            },
        },
        message="Analytics data retrieved successfully",
    )


# ──────────────────────────────────────────────
# ORDERS
# ──────────────────────────────────────────────

@admin_bp.route("/orders", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_orders():
    status = request.args.get("status")
    date_range = request.args.get("dateRange")
    search = request.args.get("search")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 10))

    query = Order.query

    if status and status != "all":
        query = query.filter(Order.status == status)

    if date_range:
        days_map = {"today": 1, "7days": 7, "30days": 30, "90days": 90}
        days = days_map.get(date_range, 7)
        since = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Order.created_at >= since)

    if search:
        query = query.join(User, Order.customer_id == User.id).filter(
            (Order.order_number.ilike(f"%{search}%")) |
            (User.name.ilike(f"%{search}%"))
        )

    query = query.order_by(desc(Order.created_at))
    result = paginate_query(query, page, per_page)

    # Stats
    total_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status == "delivered"
    ).scalar() or 0
    stats = {
        "totalRevenue": total_revenue,
        "totalOrders": Order.query.count(),
        "pendingOrders": Order.query.filter_by(status="pending").count(),
        "deliveredOrders": Order.query.filter_by(status="delivered").count(),
    }

    return success_response(
        data={
            "orders": [o.to_dict() for o in result["items"]],
            "stats": stats,
            "pagination": result["pagination"],
        },
    )


@admin_bp.route("/orders/<order_id>", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_order(order_id):
    order = Order.query.filter_by(order_number=order_id).first()
    if not order:
        return error_response("Order not found", 404)
    return success_response(data=order.to_dict())


# ──────────────────────────────────────────────
# PAYOUTS
# ──────────────────────────────────────────────

@admin_bp.route("/payouts", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_payouts():
    status = request.args.get("status")
    user_type = request.args.get("userType")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 10))

    query = Payout.query
    if status and status != "all":
        query = query.filter(Payout.status == status)
    if user_type:
        query = query.filter(Payout.user_type == user_type)

    query = query.order_by(desc(Payout.created_at))
    result = paginate_query(query, page, per_page)

    return success_response(
        data={
            "payouts": [p.to_dict() for p in result["items"]],
            "pagination": result["pagination"],
            "stats": {
                "total": Payout.query.count(),
                "pending": Payout.query.filter_by(status="pending").count(),
                "completed": Payout.query.filter_by(status="completed").count(),
                "totalAmount": db.session.query(func.sum(Payout.amount)).filter_by(status="completed").scalar() or 0,
            },
        },
    )


@admin_bp.route("/payouts/<int:payout_id>/status", methods=["PUT"])
@jwt_required()
@require_role("admin")
def update_payout_status(payout_id):
    data = request.get_json()
    payout = Payout.query.get_or_404(payout_id)
    payout.status = data.get("status", payout.status)
    if data.get("notes"):
        payout.notes = data["notes"]
    if payout.status == "completed":
        payout.processed_at = datetime.utcnow()
    db.session.commit()
    return success_response(data=payout.to_dict(), message="Payout status updated")


# ──────────────────────────────────────────────
# SETTINGS
# ──────────────────────────────────────────────

_admin_settings = {
    "platform_name": "Tumana",
    "platform_fee": 10,
    "min_order_amount": 100,
    "max_delivery_radius": 20,
    "currency": "KES",
    "support_email": "support@tumana.co.ke",
    "support_phone": "+254700000000",
    "maintenance_mode": False,
}


@admin_bp.route("/settings", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_settings():
    return success_response(data=_admin_settings)


@admin_bp.route("/settings", methods=["PUT"])
@jwt_required()
@require_role("admin")
def update_admin_settings():
    data = request.get_json()
    _admin_settings.update(data)
    return success_response(data=_admin_settings, message="Settings updated")


@admin_bp.route("/change-password", methods=["POST"])
@jwt_required()
@require_role("admin")
def change_admin_password():
    data = request.get_json()
    current_user = get_current_user()

    if not current_user.check_password(data.get("current_password", "")):
        return error_response("Current password is incorrect", 401)

    current_user.set_password(data["new_password"])
    db.session.commit()
    return success_response(message="Password changed successfully")


# ──────────────────────────────────────────────
# SUBSCRIPTIONS
# ──────────────────────────────────────────────

@admin_bp.route("/subscriptions", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_subscriptions():
    status = request.args.get("status")
    plan = request.args.get("plan")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 10))

    query = Subscription.query
    if status and status != "all":
        query = query.filter(Subscription.status == status)
    if plan:
        query = query.filter(Subscription.plan_type == plan)

    result = paginate_query(query, page, per_page)
    return success_response(
        data={
            "subscriptions": [s.to_dict() for s in result["items"]],
            "pagination": result["pagination"],
        },
    )


@admin_bp.route("/subscriptions/<int:sub_id>", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_subscription(sub_id):
    sub = Subscription.query.get_or_404(sub_id)
    return success_response(data=sub.to_dict())


@admin_bp.route("/subscriptions/<int:sub_id>/status", methods=["PUT"])
@jwt_required()
@require_role("admin")
def update_subscription_status(sub_id):
    data = request.get_json()
    sub = Subscription.query.get_or_404(sub_id)
    sub.status = data.get("status", sub.status)
    db.session.commit()
    return success_response(data=sub.to_dict(), message="Subscription status updated")


@admin_bp.route("/subscriptions/bulk", methods=["PUT"])
@jwt_required()
@require_role("admin")
def bulk_update_subscriptions():
    data = request.get_json()
    ids = data.get("ids", [])
    new_status = data.get("status")
    Subscription.query.filter(Subscription.id.in_(ids)).update(
        {"status": new_status}, synchronize_session=False
    )
    db.session.commit()
    return success_response(message=f"Updated {len(ids)} subscriptions")


@admin_bp.route("/subscriptions/stats", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_subscription_stats():
    return success_response(
        data={
            "total": Subscription.query.count(),
            "active": Subscription.query.filter_by(status="active").count(),
            "trial": Subscription.query.filter_by(status="trial").count(),
            "cancelled": Subscription.query.filter_by(status="cancelled").count(),
            "monthly_revenue": db.session.query(func.sum(Subscription.amount)).filter_by(status="active", billing_cycle="monthly").scalar() or 0,
        }
    )


# ──────────────────────────────────────────────
# USERS
# ──────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_users():
    role = request.args.get("role")
    status = request.args.get("status")
    search = request.args.get("search")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 10))

    query = User.query
    if role:
        query = query.filter(User.role == role)
    if status and status != "all":
        query = query.filter(User.status == status)
    if search:
        query = query.filter(
            (User.name.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%")) |
            (User.phone.ilike(f"%{search}%"))
        )

    query = query.order_by(desc(User.created_at))
    result = paginate_query(query, page, per_page)

    return success_response(
        data={
            "users": [u.to_dict() for u in result["items"]],
            "pagination": result["pagination"],
        },
    )


@admin_bp.route("/users/stats", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_user_stats():
    return success_response(
        data={
            "total": User.query.count(),
            "customers": User.query.filter_by(role="customer").count(),
            "riders": User.query.filter_by(role="rider").count(),
            "shopOwners": User.query.filter_by(role="shop_owner").count(),
            "admins": User.query.filter_by(role="admin").count(),
            "active": User.query.filter_by(status="active").count(),
            "suspended": User.query.filter_by(status="suspended").count(),
        }
    )


@admin_bp.route("/users/<int:user_id>", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_user(user_id):
    user = User.query.get_or_404(user_id)
    return success_response(data=user.to_dict())


@admin_bp.route("/users/<int:user_id>/status", methods=["PUT"])
@jwt_required()
@require_role("admin")
def update_admin_user_status(user_id):
    data = request.get_json()
    user = User.query.get_or_404(user_id)
    user.status = data.get("status", user.status)
    db.session.commit()
    return success_response(data=user.to_dict(), message="User status updated")


@admin_bp.route("/users/<int:user_id>/verify", methods=["POST", "PUT"])
@jwt_required()
@require_role("admin")
def verify_admin_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_verified = True
    user.status = "active"
    db.session.commit()
    return success_response(data=user.to_dict(), message="User verified")


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@jwt_required()
@require_role("admin")
def delete_admin_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return success_response(message="User deleted")


@admin_bp.route("/users/bulk", methods=["PUT"])
@jwt_required()
@require_role("admin")
def bulk_update_admin_users():
    data = request.get_json()
    ids = data.get("ids", data.get("user_ids", []))
    action = data.get("action")
    if action in ("suspend",):
        User.query.filter(User.id.in_(ids)).update({"status": "suspended"}, synchronize_session=False)
    elif action in ("activate",):
        User.query.filter(User.id.in_(ids)).update({"status": "active"}, synchronize_session=False)
    elif action in ("verify",):
        User.query.filter(User.id.in_(ids)).update({"is_verified": True, "status": "active"}, synchronize_session=False)
    elif action in ("delete",):
        User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return success_response(message=f"Updated {len(ids)} users")


# ──────────────────────────────────────────────
# SHOPS (admin)
# ──────────────────────────────────────────────

@admin_bp.route("/shops", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_shops():
    status = request.args.get("status")
    search = request.args.get("search")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 10))

    query = Shop.query
    if status and status != "all":
        query = query.filter(Shop.status == status)
    if search:
        query = query.filter(Shop.name.ilike(f"%{search}%"))
    query = query.order_by(desc(Shop.created_at))
    result = paginate_query(query, page, per_page)

    return success_response(
        data={
            "shops": [s.to_dict() for s in result["items"]],
            "pagination": result["pagination"],
            "stats": {
                "total": Shop.query.count(),
                "active": Shop.query.filter_by(status="active").count(),
                "pending": Shop.query.filter_by(status="pending").count(),
                "suspended": Shop.query.filter_by(status="suspended").count(),
            },
        }
    )


@admin_bp.route("/shops/<int:shop_id>", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    return success_response(data=shop.to_dict())


@admin_bp.route("/shops/<int:shop_id>/status", methods=["PUT"])
@jwt_required()
@require_role("admin")
def update_admin_shop_status(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    data = request.get_json()
    shop.status = data.get("status", shop.status)
    db.session.commit()
    return success_response(data=shop.to_dict(), message="Shop status updated")


# ──────────────────────────────────────────────
# DASHBOARD & NOTIFICATIONS
# ──────────────────────────────────────────────

@admin_bp.route("/dashboard", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_dashboard():
    time_range = request.args.get("timeRange", "7days")
    days_map = {"7days": 7, "30days": 30}
    days = days_map.get(time_range, 7)
    since = datetime.utcnow() - timedelta(days=days)

    return success_response(
        data={
            "stats": {
                "totalRevenue": db.session.query(func.sum(Order.total_amount)).filter(
                    Order.status == "delivered", Order.created_at >= since
                ).scalar() or 0,
                "totalOrders": Order.query.filter(Order.created_at >= since).count(),
                "newUsers": User.query.filter(User.created_at >= since).count(),
                "activeShops": Shop.query.filter_by(status="active").count(),
            },
        }
    )


@admin_bp.route("/notifications", methods=["GET"])
@jwt_required()
@require_role("admin")
def get_admin_notifications():
    admin = get_current_user()
    notifications = Notification.query.filter_by(user_id=admin.id).order_by(
        desc(Notification.created_at)
    ).limit(50).all()
    return success_response(
        data={
            "notifications": [n.to_dict() for n in notifications],
            "unread_count": sum(1 for n in notifications if not n.is_read),
        }
    )


@admin_bp.route("/notifications/<int:notif_id>/read", methods=["PUT"])
@jwt_required()
@require_role("admin")
def mark_notification_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    notif.is_read = True
    notif.read_at = datetime.utcnow()
    db.session.commit()
    return success_response(message="Notification marked as read")


@admin_bp.route("/notifications/read-all", methods=["PUT"])
@jwt_required()
@require_role("admin")
def mark_all_notifications_read():
    admin = get_current_user()
    Notification.query.filter_by(user_id=admin.id, is_read=False).update(
        {"is_read": True, "read_at": datetime.utcnow()}, synchronize_session=False
    )
    db.session.commit()
    return success_response(message="All notifications marked as read")

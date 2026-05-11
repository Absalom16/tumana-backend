from datetime import datetime, timedelta
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from sqlalchemy import desc, func
from app import db
from app.models.user import User
from app.models.order import Order, OrderStatusHistory
from app.models.delivery import Delivery, RiderLocation
from app.models.wallet import Wallet, WalletTransaction
from app.models.payout import Payout
from app.utils.helpers import (
    success_response, error_response, require_role,
    get_current_user, paginate_query,
)

rider_bp = Blueprint("rider", __name__)


# ──────────────────────────────────────────────
# DASHBOARD & STATS
# ──────────────────────────────────────────────

@rider_bp.route("/dashboard", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_rider_dashboard():
    rider = get_current_user()
    active = Delivery.query.filter_by(rider_id=rider.id, status="in_transit").count()
    completed_today = Delivery.query.filter(
        Delivery.rider_id == rider.id,
        Delivery.status == "delivered",
        Delivery.delivered_at >= datetime.utcnow().replace(hour=0, minute=0, second=0),
    ).count()
    wallet = Wallet.query.filter_by(user_id=rider.id).first()
    location = RiderLocation.query.filter_by(rider_id=rider.id).first()

    return success_response(
        data={
            "rider": rider.to_dict(),
            "is_online": location.is_online if location else False,
            "active_deliveries": active,
            "completed_today": completed_today,
            "wallet_balance": wallet.balance if wallet else 0,
        }
    )


@rider_bp.route("/stats", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_rider_stats():
    rider = get_current_user()
    try:
        days = max(1, int(request.args.get("days", 7)))
    except (ValueError, TypeError):
        days = 7
    since = datetime.utcnow() - timedelta(days=days)

    deliveries = Delivery.query.filter(
        Delivery.rider_id == rider.id,
        Delivery.created_at >= since,
    ).all()

    total = len(deliveries)
    completed = sum(1 for d in deliveries if d.status == "delivered")
    cancelled = sum(1 for d in deliveries if d.status == "cancelled")
    earnings = db.session.query(func.sum(Delivery.rider_earnings)).filter(
        Delivery.rider_id == rider.id,
        Delivery.status == "delivered",
        Delivery.delivered_at >= since,
    ).scalar() or 0

    return success_response(
        data={
            "total_deliveries": total,
            "completed_deliveries": completed,
            "cancelled_deliveries": cancelled,
            "completion_rate": (completed / total * 100) if total else 0,
            "earnings": earnings,
            "period_days": days,
        }
    )


# ──────────────────────────────────────────────
# JOBS
# ──────────────────────────────────────────────

@rider_bp.route("/available-jobs", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_available_jobs():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(100, max(1, int(request.args.get("perPage", 10))))
    except (ValueError, TypeError):
        per_page = 10

    # Available jobs = confirmed/preparing/ready orders with no rider assigned
    query = Order.query.filter(
        Order.status.in_(["confirmed", "preparing", "ready"]),
        Order.rider_id == None,
    ).order_by(Order.created_at)

    result = paginate_query(query, page, per_page)
    return success_response(
        data={
            "jobs": [o.to_dict() for o in result["items"]],
            "pagination": result["pagination"],
        }
    )


@rider_bp.route("/jobs/<job_id>", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_job(job_id):
    order = Order.query.filter_by(order_number=job_id).first_or_404()
    return success_response(data=order.to_dict())


@rider_bp.route("/jobs/<job_id>/accept", methods=["POST"])
@jwt_required()
@require_role("rider")
def accept_job(job_id):
    rider = get_current_user()
    order = Order.query.filter_by(order_number=job_id).first_or_404()

    if order.rider_id:
        return error_response("Job already taken")
    if order.status not in ("confirmed", "preparing", "ready"):
        return error_response("Job is no longer available")

    order.rider_id = rider.id

    delivery = Delivery.query.filter_by(order_id=order.id).first()
    if not delivery:
        delivery = Delivery(order_id=order.id, rider_id=rider.id, status="assigned")
        db.session.add(delivery)
    else:
        delivery.rider_id = rider.id
        delivery.status = "assigned"
        delivery.accepted_at = datetime.utcnow()

    history = OrderStatusHistory(order_id=order.id, status="assigned", changed_by=rider.id)
    db.session.add(history)
    db.session.commit()

    return success_response(data=order.to_dict(), message="Job accepted")


@rider_bp.route("/jobs/<job_id>/decline", methods=["POST"])
@jwt_required()
@require_role("rider")
def decline_job(job_id):
    # Just log the decline - job stays available for other riders
    return success_response(message="Job declined")


@rider_bp.route("/jobs/suggestions", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_job_suggestions():
    rider = get_current_user()
    location = RiderLocation.query.filter_by(rider_id=rider.id).first()

    # In production, use geospatial query to find nearby orders
    available = Order.query.filter(
        Order.status.in_(["confirmed", "preparing", "ready"]),
        Order.rider_id == None,
    ).limit(5).all()

    return success_response(data={"suggestions": [o.to_dict() for o in available]})


@rider_bp.route("/jobs/statistics", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_job_statistics():
    rider = get_current_user()
    total = Delivery.query.filter_by(rider_id=rider.id).count()
    completed = Delivery.query.filter_by(rider_id=rider.id, status="delivered").count()
    return success_response(
        data={
            "total_jobs": total,
            "completed_jobs": completed,
            "acceptance_rate": 85.5,  # Would be calculated from accepted/offered ratio
        }
    )


# ──────────────────────────────────────────────
# DELIVERIES
# ──────────────────────────────────────────────

@rider_bp.route("/deliveries", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_rider_deliveries():
    rider = get_current_user()
    status = request.args.get("status")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(100, max(1, int(request.args.get("perPage", 10))))
    except (ValueError, TypeError):
        per_page = 10

    query = Delivery.query.filter_by(rider_id=rider.id)
    if status and status != "all":
        query = query.filter_by(status=status)
    query = query.order_by(desc(Delivery.created_at))

    result = paginate_query(query, page, per_page)
    return success_response(
        data={
            "deliveries": [d.to_dict() for d in result["items"]],
            "pagination": result["pagination"],
        }
    )


@rider_bp.route("/deliveries/active", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_active_deliveries():
    rider = get_current_user()
    deliveries = Delivery.query.filter(
        Delivery.rider_id == rider.id,
        Delivery.status.in_(["assigned", "picked_up", "in_transit"]),
    ).all()
    return success_response(data={"deliveries": [d.to_dict() for d in deliveries]})


@rider_bp.route("/deliveries/completed", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_completed_deliveries():
    rider = get_current_user()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(100, max(1, int(request.args.get("perPage", 10))))
    except (ValueError, TypeError):
        per_page = 10

    query = Delivery.query.filter_by(rider_id=rider.id, status="delivered").order_by(
        desc(Delivery.delivered_at)
    )
    result = paginate_query(query, page, per_page)
    return success_response(
        data={
            "deliveries": [d.to_dict() for d in result["items"]],
            "pagination": result["pagination"],
        }
    )


@rider_bp.route("/deliveries/<int:delivery_id>", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_delivery(delivery_id):
    rider = get_current_user()
    delivery = Delivery.query.filter_by(id=delivery_id, rider_id=rider.id).first()
    if not delivery:
        return error_response("Delivery not found", 404)
    return success_response(data=delivery.to_dict())


@rider_bp.route("/deliveries/<int:delivery_id>/status", methods=["PUT"])
@jwt_required()
@require_role("rider")
def update_delivery_status(delivery_id):
    rider = get_current_user()
    delivery = Delivery.query.filter_by(id=delivery_id, rider_id=rider.id).first()
    if not delivery:
        return error_response("Delivery not found", 404)

    data = request.get_json()
    new_status = data.get("status")

    valid_transitions = {
        "assigned": ["picked_up"],
        "picked_up": ["in_transit"],
        "in_transit": ["delivered"],
    }

    if new_status not in valid_transitions.get(delivery.status, []):
        return error_response(f"Cannot transition from {delivery.status} to {new_status}")

    delivery.status = new_status
    if new_status == "picked_up":
        delivery.picked_up_at = datetime.utcnow()
        delivery.order.status = "picked_up"
    elif new_status == "in_transit":
        delivery.order.status = "in_transit"
    elif new_status == "delivered":
        delivery.delivered_at = datetime.utcnow()
        delivery.order.status = "delivered"
        delivery.order.delivered_at = datetime.utcnow()
        # Credit rider earnings
        if delivery.rider_earnings:
            _credit_rider_wallet(rider.id, delivery.rider_earnings, f"Delivery #{delivery_id} earnings")

    history = OrderStatusHistory(order_id=delivery.order_id, status=new_status, changed_by=rider.id)
    db.session.add(history)
    db.session.commit()

    return success_response(data=delivery.to_dict(), message="Status updated")


@rider_bp.route("/deliveries/<int:delivery_id>/cancel", methods=["POST"])
@jwt_required()
@require_role("rider")
def cancel_delivery(delivery_id):
    rider = get_current_user()
    delivery = Delivery.query.filter_by(id=delivery_id, rider_id=rider.id).first()
    if not delivery:
        return error_response("Delivery not found", 404)

    data = request.get_json() or {}
    delivery.status = "cancelled"
    delivery.cancelled_at = datetime.utcnow()
    delivery.cancellation_reason = data.get("reason")
    delivery.order.rider_id = None
    db.session.commit()

    return success_response(message="Delivery cancelled")


@rider_bp.route("/deliveries/stats", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_delivery_stats():
    rider = get_current_user()
    total = Delivery.query.filter_by(rider_id=rider.id).count()
    completed = Delivery.query.filter_by(rider_id=rider.id, status="delivered").count()
    total_earnings = db.session.query(func.sum(Delivery.rider_earnings)).filter_by(
        rider_id=rider.id, status="delivered"
    ).scalar() or 0

    return success_response(
        data={
            "total_deliveries": total,
            "completed_deliveries": completed,
            "completion_rate": (completed / total * 100) if total else 0,
            "total_earnings": total_earnings,
        }
    )


# ──────────────────────────────────────────────
# ORDERS (legacy endpoints)
# ──────────────────────────────────────────────

@rider_bp.route("/orders/<order_id>/<status>", methods=["PUT"])
@jwt_required()
@require_role("rider")
def update_order_delivery_status(order_id, status):
    rider = get_current_user()
    order = Order.query.filter_by(order_number=order_id, rider_id=rider.id).first()
    if not order:
        return error_response("Order not found", 404)

    allowed_statuses = ["picked_up", "in_transit", "delivered"]
    if status not in allowed_statuses:
        return error_response("Invalid status")

    order.status = status
    if status == "delivered":
        order.delivered_at = datetime.utcnow()

    history = OrderStatusHistory(order_id=order.id, status=status, changed_by=rider.id)
    db.session.add(history)
    db.session.commit()

    return success_response(data=order.to_dict(), message="Order status updated")


# ──────────────────────────────────────────────
# LOCATION & ONLINE STATUS
# ──────────────────────────────────────────────

@rider_bp.route("/location", methods=["PUT", "POST"])
@jwt_required()
@require_role("rider")
def update_rider_location():
    rider = get_current_user()
    data = request.get_json()

    location = RiderLocation.query.filter_by(rider_id=rider.id).first()
    if not location:
        location = RiderLocation(rider_id=rider.id, latitude=0, longitude=0)
        db.session.add(location)

    location.latitude = data.get("latitude", location.latitude)
    location.longitude = data.get("longitude", location.longitude)
    db.session.commit()

    return success_response(message="Location updated")


@rider_bp.route("/online-status", methods=["PUT", "POST"])
@jwt_required()
@require_role("rider")
def toggle_online_status():
    rider = get_current_user()
    data = request.get_json()
    is_online = data.get("isOnline", data.get("online_status", False))

    location = RiderLocation.query.filter_by(rider_id=rider.id).first()
    if not location:
        location = RiderLocation(rider_id=rider.id, latitude=0, longitude=0, is_online=is_online)
        db.session.add(location)
    else:
        location.is_online = is_online

    db.session.commit()
    return success_response(data={"is_online": is_online}, message="Status updated")


# ──────────────────────────────────────────────
# EARNINGS & WALLET
# ──────────────────────────────────────────────

@rider_bp.route("/earnings", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_rider_earnings():
    rider = get_current_user()
    period = request.args.get("period", "weekly")
    days = {"daily": 1, "weekly": 7, "monthly": 30}.get(period, 7)
    since = datetime.utcnow() - timedelta(days=days)

    total = db.session.query(func.sum(Delivery.rider_earnings)).filter(
        Delivery.rider_id == rider.id,
        Delivery.status == "delivered",
        Delivery.delivered_at >= since,
    ).scalar() or 0

    deliveries = Delivery.query.filter(
        Delivery.rider_id == rider.id,
        Delivery.status == "delivered",
        Delivery.delivered_at >= since,
    ).all()

    return success_response(
        data={
            "period": period,
            "total_earnings": total,
            "total_deliveries": len(deliveries),
            "average_per_delivery": total / len(deliveries) if deliveries else 0,
        }
    )


@rider_bp.route("/wallet", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_rider_wallet():
    rider = get_current_user()
    wallet = Wallet.query.filter_by(user_id=rider.id).first()
    if not wallet:
        wallet = Wallet(user_id=rider.id)
        db.session.add(wallet)
        db.session.commit()

    recent_txns = WalletTransaction.query.filter_by(wallet_id=wallet.id).order_by(
        desc(WalletTransaction.created_at)
    ).limit(10).all()

    return success_response(
        data={
            "balance": wallet.balance,
            "currency": wallet.currency,
            "recent_transactions": [t.to_dict() for t in recent_txns],
        }
    )


@rider_bp.route("/earnings/withdraw", methods=["POST"])
@jwt_required()
@require_role("rider")
def withdraw_earnings():
    rider = get_current_user()
    data = request.get_json()
    amount = float(data.get("amount", 0))

    wallet = Wallet.query.filter_by(user_id=rider.id).first()
    if not wallet or wallet.balance < amount:
        return error_response("Insufficient balance")

    balance_before = wallet.balance
    wallet.balance -= amount

    txn = WalletTransaction(
        wallet_id=wallet.id,
        transaction_type="debit",
        amount=amount,
        balance_before=balance_before,
        balance_after=wallet.balance,
        description="Earnings withdrawal",
        payment_method=data.get("payment_method", "mpesa"),
        status="completed",
    )
    db.session.add(txn)

    payout = Payout(
        user_id=rider.id,
        user_type="rider",
        amount=amount,
        status="pending",
        payment_method=data.get("payment_method", "mpesa"),
    )
    db.session.add(payout)
    db.session.commit()

    return success_response(data={"new_balance": wallet.balance}, message="Withdrawal request submitted")


# ──────────────────────────────────────────────
# PERFORMANCE & ACHIEVEMENTS
# ──────────────────────────────────────────────

@rider_bp.route("/performance", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_rider_performance():
    rider = get_current_user()
    time_range = request.args.get("timeRange", "30days")
    days = int(time_range.replace("days", ""))
    since = datetime.utcnow() - timedelta(days=days)

    deliveries = Delivery.query.filter(
        Delivery.rider_id == rider.id,
        Delivery.created_at >= since,
    ).all()

    completed = [d for d in deliveries if d.status == "delivered"]
    return success_response(
        data={
            "total_deliveries": len(deliveries),
            "completed_deliveries": len(completed),
            "completion_rate": (len(completed) / len(deliveries) * 100) if deliveries else 0,
            "on_time_rate": 92.5,  # Would calculate from actual timestamps
            "average_rating": 4.7,  # Would calculate from order ratings
        }
    )


@rider_bp.route("/achievements", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_rider_achievements():
    rider = get_current_user()
    total_deliveries = Delivery.query.filter_by(rider_id=rider.id, status="delivered").count()

    achievements = []
    if total_deliveries >= 1:
        achievements.append({"title": "First Delivery", "description": "Completed your first delivery", "unlocked": True})
    if total_deliveries >= 10:
        achievements.append({"title": "Speed Racer", "description": "10 deliveries completed", "unlocked": True})
    if total_deliveries >= 50:
        achievements.append({"title": "Road Warrior", "description": "50 deliveries completed", "unlocked": True})
    if total_deliveries >= 100:
        achievements.append({"title": "Century Club", "description": "100 deliveries completed", "unlocked": True})

    return success_response(data={"achievements": achievements, "total_deliveries": total_deliveries})


@rider_bp.route("/rankings", methods=["GET"])
@jwt_required()
@require_role("rider")
def get_rider_rankings():
    # Top 10 riders by completed deliveries
    from sqlalchemy import func
    rankings = db.session.query(
        User,
        func.count(Delivery.id).label("deliveries")
    ).join(Delivery, User.id == Delivery.rider_id).filter(
        Delivery.status == "delivered"
    ).group_by(User.id).order_by(desc("deliveries")).limit(10).all()

    return success_response(
        data={
            "rankings": [
                {
                    "rank": idx + 1,
                    "rider_name": user.name,
                    "deliveries": count,
                }
                for idx, (user, count) in enumerate(rankings)
            ]
        }
    )


# ──────────────────────────────────────────────
# HELPER
# ──────────────────────────────────────────────

def _credit_rider_wallet(rider_id, amount, description):
    wallet = Wallet.query.filter_by(user_id=rider_id).first()
    if not wallet:
        wallet = Wallet(user_id=rider_id)
        db.session.add(wallet)
        db.session.flush()

    balance_before = wallet.balance
    wallet.balance += amount

    txn = WalletTransaction(
        wallet_id=wallet.id,
        transaction_type="credit",
        amount=amount,
        balance_before=balance_before,
        balance_after=wallet.balance,
        description=description,
        status="completed",
    )
    db.session.add(txn)

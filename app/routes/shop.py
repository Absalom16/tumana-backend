from datetime import datetime, timedelta
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from sqlalchemy import desc, func
from app import db
from app.models.shop import Shop, Product, ProductCategory, Review
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.payout import Payout
from app.models.wallet import Wallet, WalletTransaction
from app.models.subscription import Subscription
from app.utils.helpers import (
    success_response, error_response, require_role,
    get_current_user, paginate_query,
)

shop_bp = Blueprint("shop", __name__)


def _get_owner_shop(user):
    shop = Shop.query.filter_by(owner_id=user.id).first()
    if not shop:
        raise ValueError("Shop not found for this user")
    return shop


# ──────────────────────────────────────────────
# PROFILE
# ──────────────────────────────────────────────

@shop_bp.route("/profile", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_shop_profile():
    user = get_current_user()
    try:
        shop = _get_owner_shop(user)
    except ValueError:
        return error_response("Shop not found", 404)
    return success_response(data=shop.to_dict())


@shop_bp.route("/profile", methods=["PUT"])
@jwt_required()
@require_role("shop_owner")
def update_shop_profile():
    user = get_current_user()
    try:
        shop = _get_owner_shop(user)
    except ValueError:
        return error_response("Shop not found", 404)

    data = request.get_json()
    fields = [
        "name", "description", "address", "phone", "email",
        "opening_time", "closing_time", "min_order_amount", "delivery_fee",
        "avg_delivery_time", "is_open",
    ]
    for field in fields:
        if field in data:
            setattr(shop, field, data[field])

    db.session.commit()
    return success_response(data=shop.to_dict(), message="Profile updated")


# ──────────────────────────────────────────────
# DASHBOARD & ANALYTICS
# ──────────────────────────────────────────────

@shop_bp.route("/dashboard", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_shop_dashboard():
    user = get_current_user()
    try:
        shop = _get_owner_shop(user)
    except ValueError:
        return error_response("Shop not found", 404)

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_orders = Order.query.filter(Order.shop_id == shop.id, Order.created_at >= today).count()
    today_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        Order.shop_id == shop.id,
        Order.status == "delivered",
        Order.created_at >= today,
    ).scalar() or 0
    pending = Order.query.filter_by(shop_id=shop.id, status="pending").count()
    total_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        Order.shop_id == shop.id, Order.status == "delivered"
    ).scalar() or 0
    total_orders = Order.query.filter_by(shop_id=shop.id).count()

    recent_orders = Order.query.filter_by(shop_id=shop.id).order_by(
        desc(Order.created_at)
    ).limit(5).all()

    return success_response(
        data={
            "profile": shop.to_dict(),
            "shop": shop.to_dict(),
            "today_orders": today_orders,
            "today_revenue": float(today_revenue),
            "pending_orders": pending,
            "total_products": Product.query.filter_by(shop_id=shop.id).count(),
            "total_orders": total_orders,
            "total_revenue": float(total_revenue),
            "orders": [o.to_dict() for o in recent_orders],
            "analytics": {
                "total_orders": total_orders,
                "total_revenue": float(total_revenue),
                "avg_order_value": float(total_revenue / total_orders) if total_orders else 0,
                "pending_orders": pending,
                "today_orders": today_orders,
                "today_revenue": float(today_revenue),
            },
        }
    )


@shop_bp.route("/analytics", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_shop_analytics():
    user = get_current_user()
    try:
        shop = _get_owner_shop(user)
    except ValueError:
        return error_response("Shop not found", 404)

    days = int(request.args.get("days", 30))
    since = datetime.utcnow() - timedelta(days=days)
    prev_since = since - timedelta(days=days)

    orders = Order.query.filter(Order.shop_id == shop.id, Order.created_at >= since).all()
    prev_orders = Order.query.filter(Order.shop_id == shop.id, Order.created_at >= prev_since, Order.created_at < since).all()

    total_revenue = sum(o.total_amount for o in orders if o.status == "delivered")
    prev_revenue = sum(o.total_amount for o in prev_orders if o.status == "delivered")

    # Daily data
    daily_orders = []
    for i in range(days):
        day = since + timedelta(days=i)
        day_end = day + timedelta(days=1)
        day_rev = sum(o.total_amount for o in orders if day <= o.created_at < day_end and o.status == "delivered")
        day_count = sum(1 for o in orders if day <= o.created_at < day_end)
        daily_orders.append({
            "date": day.strftime("%b %d"),
            "orders": day_count,
            "revenue": day_rev
        })

    # Top Products
    top_products_query = db.session.query(
        Product.id, Product.name, func.count(OrderItem.id).label("orders"), func.sum(OrderItem.total_price).label("revenue")
    ).join(OrderItem, Product.id == OrderItem.product_id).join(Order, Order.id == OrderItem.order_id).filter(
        Order.shop_id == shop.id, Order.created_at >= since
    ).group_by(Product.id).order_by(desc("orders")).limit(10).all()

    top_products = []
    total_product_orders = sum(p.orders for p in top_products_query)
    for p in top_products_query:
        top_products.append({
            "id": p.id,
            "name": p.name,
            "orders": p.orders,
            "revenue": float(p.revenue) if p.revenue else 0,
            "percentage": (p.orders / total_product_orders * 100) if total_product_orders else 0
        })

    # Customer Segments
    total_cust = db.session.query(func.count(func.distinct(Order.customer_id))).filter(Order.shop_id == shop.id).scalar() or 0
    new_cust = db.session.query(func.count(func.distinct(Order.customer_id))).filter(Order.shop_id == shop.id, Order.created_at >= since).scalar() or 0
    returning_cust = total_cust - new_cust
    customer_segments = [
        {"name": "New Customers", "value": (new_cust / total_cust * 100) if total_cust else 0, "color": "#3b82f6"},
        {"name": "Returning Customers", "value": (returning_cust / total_cust * 100) if total_cust else 0, "color": "#10b981"},
    ]

    # Order Status Distribution
    status_counts = db.session.query(Order.status, func.count(Order.id)).filter(Order.shop_id == shop.id, Order.created_at >= since).group_by(Order.status).all()
    total_order_count = len(orders)
    order_status = []
    colors = {"delivered": "#10b981", "pending": "#f59e0b", "cancelled": "#ef4444", "ready": "#8b5cf6", "preparing": "#3b82f6", "confirmed": "#6366f1"}
    for status, count in status_counts:
        order_status.append({
            "name": status.capitalize(),
            "value": (count / total_order_count * 100) if total_order_count else 0,
            "color": colors.get(status, "#94a3b8")
        })

    # Peak Hours
    hour_counts = {}
    for o in orders:
        h = o.created_at.hour
        hour_counts[h] = hour_counts.get(h, 0) + 1
    peak_hours = [{"hour": f"{h:02d}:00", "orders": hour_counts.get(h, 0)} for h in range(24)]

    # Growth rates
    rev_growth = ((total_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue else 0
    order_growth = ((len(orders) - len(prev_orders)) / len(prev_orders) * 100) if len(prev_orders) else 0

    return success_response(
        data={
            "summary": {
                "total_orders": len(orders),
                "total_revenue": total_revenue,
                "avg_order_value": total_revenue / len(orders) if orders else 0,
                "active_customers": new_cust,
                "avg_rating": float(shop.rating) if shop.rating else 0,
                "repeat_customers": returning_cust,
                "total_customers": total_cust,
                "growth_rate": round(order_growth, 1),
                "completion_rate": 94, # Hardcoded for now or calculate from statuses
            },
            "daily_orders": daily_orders,
            "top_products": top_products,
            "customer_segments": customer_segments,
            "order_status": order_status,
            "peak_hours": peak_hours,
            "time_period": f"{days} days",
            "trends": {
                "orders_trend": f"{'+' if order_growth >= 0 else ''}{round(order_growth, 1)}%",
                "revenue_trend": f"{'+' if rev_growth >= 0 else ''}{round(rev_growth, 1)}%",
            }
        }
    )


@shop_bp.route("/analytics/revenue", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_revenue_analytics():
    user = get_current_user()
    shop = _get_owner_shop(user)
    time_range = request.args.get("timeRange", "30days")
    days = int(time_range.replace("days", "")) if "days" in time_range else 30
    since = datetime.utcnow() - timedelta(days=days)

    total = db.session.query(func.sum(Order.total_amount)).filter(
        Order.shop_id == shop.id, Order.status == "delivered", Order.created_at >= since
    ).scalar() or 0

    return success_response(data={"total_revenue": total, "period": time_range})


@shop_bp.route("/analytics/products", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_product_performance_analytics():
    user = get_current_user()
    shop = _get_owner_shop(user)
    products = Product.query.filter_by(shop_id=shop.id).order_by(desc(Product.total_orders)).limit(10).all()
    return success_response(data={"top_products": [p.to_dict() for p in products]})


@shop_bp.route("/analytics/customers", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_customer_analytics():
    user = get_current_user()
    shop = _get_owner_shop(user)
    from app.models.user import User as UserModel
    unique_customers = db.session.query(func.count(func.distinct(Order.customer_id))).filter_by(
        shop_id=shop.id
    ).scalar() or 0
    return success_response(data={"unique_customers": unique_customers})


@shop_bp.route("/analytics/peak-hours", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_peak_hours_analytics():
    user = get_current_user()
    shop = _get_owner_shop(user)
    # Group orders by hour
    orders = Order.query.filter_by(shop_id=shop.id).all()
    hour_counts = {}
    for o in orders:
        h = o.created_at.hour
        hour_counts[h] = hour_counts.get(h, 0) + 1

    peak_data = [{"hour": f"{h:02d}:00", "orders": hour_counts.get(h, 0)} for h in range(24)]
    return success_response(data={"peak_hours": peak_data})


@shop_bp.route("/analytics/export", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def export_analytics_report():
    # In production, generate CSV/PDF and return download URL
    return success_response(
        data={"download_url": "/api/shop/analytics/export/file", "expires_in": 3600},
        message="Report generation started",
    )


# ──────────────────────────────────────────────
# PRODUCTS
# ──────────────────────────────────────────────

@shop_bp.route("/products", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_shop_products():
    user = get_current_user()
    try:
        shop = _get_owner_shop(user)
    except ValueError:
        return error_response("Shop not found", 404)

    category_id = request.args.get("categoryId")
    search = request.args.get("search")
    is_available = request.args.get("isAvailable")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 20))

    query = Product.query.filter_by(shop_id=shop.id)
    if category_id:
        query = query.filter_by(category_id=int(category_id))
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if is_available is not None:
        query = query.filter_by(is_available=is_available == "true")

    result = paginate_query(query, page, per_page)
    return success_response(
        data={
            "products": [p.to_dict() for p in result["items"]],
            "pagination": result["pagination"],
        }
    )


@shop_bp.route("/products/<int:product_id>", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_shop_product(product_id):
    user = get_current_user()
    shop = _get_owner_shop(user)
    product = Product.query.filter_by(id=product_id, shop_id=shop.id).first()
    if not product:
        return error_response("Product not found", 404)
    return success_response(data=product.to_dict())


@shop_bp.route("/products", methods=["POST"])
@jwt_required()
@require_role("shop_owner")
def add_shop_product():
    user = get_current_user()
    try:
        shop = _get_owner_shop(user)
    except ValueError:
        return error_response("Shop not found", 404)

    data = request.get_json()
    product = Product(
        shop_id=shop.id,
        category_id=data.get("category_id"),
        name=data.get("name", ""),
        description=data.get("description"),
        price=float(data.get("price", 0)),
        image_url=data.get("image_url"),
        is_available=data.get("is_available", True),
        is_featured=data.get("is_featured", False),
        preparation_time=data.get("preparation_time", 15),
        tags=data.get("tags"),
    )
    db.session.add(product)
    db.session.commit()
    return success_response(data=product.to_dict(), message="Product added", status_code=201)


@shop_bp.route("/products/<int:product_id>", methods=["PUT"])
@jwt_required()
@require_role("shop_owner")
def update_shop_product(product_id):
    user = get_current_user()
    shop = _get_owner_shop(user)
    product = Product.query.filter_by(id=product_id, shop_id=shop.id).first()
    if not product:
        return error_response("Product not found", 404)

    data = request.get_json()
    fields = ["name", "description", "price", "image_url", "is_available", "is_featured",
              "preparation_time", "tags", "category_id"]
    for field in fields:
        if field in data:
            setattr(product, field, data[field])

    db.session.commit()
    return success_response(data=product.to_dict(), message="Product updated")


@shop_bp.route("/products/<int:product_id>", methods=["DELETE"])
@jwt_required()
@require_role("shop_owner")
def delete_shop_product(product_id):
    user = get_current_user()
    shop = _get_owner_shop(user)
    product = Product.query.filter_by(id=product_id, shop_id=shop.id).first()
    if not product:
        return error_response("Product not found", 404)
    db.session.delete(product)
    db.session.commit()
    return success_response(message="Product deleted")


@shop_bp.route("/products/<int:product_id>/toggle-availability", methods=["PUT"])
@jwt_required()
@require_role("shop_owner")
def toggle_product_availability(product_id):
    user = get_current_user()
    shop = _get_owner_shop(user)
    product = Product.query.filter_by(id=product_id, shop_id=shop.id).first()
    if not product:
        return error_response("Product not found", 404)
    product.is_available = not product.is_available
    db.session.commit()
    return success_response(data={"is_available": product.is_available}, message="Availability toggled")


@shop_bp.route("/products/<int:product_id>/toggle-featured", methods=["PUT"])
@jwt_required()
@require_role("shop_owner")
def toggle_product_featured(product_id):
    user = get_current_user()
    shop = _get_owner_shop(user)
    product = Product.query.filter_by(id=product_id, shop_id=shop.id).first()
    if not product:
        return error_response("Product not found", 404)
    product.is_featured = not product.is_featured
    db.session.commit()
    return success_response(data={"is_featured": product.is_featured}, message="Featured status toggled")


@shop_bp.route("/products/categories", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_product_categories():
    user = get_current_user()
    try:
        shop = _get_owner_shop(user)
    except ValueError:
        return error_response("Shop not found", 404)
    categories = ProductCategory.query.filter_by(shop_id=shop.id, is_active=True).all()
    return success_response(data={"categories": [c.to_dict() for c in categories]})


@shop_bp.route("/products/stats", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_product_stats():
    user = get_current_user()
    shop = _get_owner_shop(user)
    total = Product.query.filter_by(shop_id=shop.id).count()
    available = Product.query.filter_by(shop_id=shop.id, is_available=True).count()
    featured = Product.query.filter_by(shop_id=shop.id, is_featured=True).count()
    return success_response(data={"total": total, "available": available, "featured": featured})


# ──────────────────────────────────────────────
# ORDERS
# ──────────────────────────────────────────────

@shop_bp.route("/orders", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_shop_orders():
    user = get_current_user()
    try:
        shop = _get_owner_shop(user)
    except ValueError:
        return error_response("Shop not found", 404)

    status = request.args.get("status")
    search = request.args.get("search")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 10))

    query = Order.query.filter_by(shop_id=shop.id)
    if status and status != "all":
        query = query.filter_by(status=status)
    if search:
        query = query.filter(Order.order_number.ilike(f"%{search}%"))

    query = query.order_by(desc(Order.created_at))
    result = paginate_query(query, page, per_page)

    return success_response(
        data={
            "orders": [o.to_dict() for o in result["items"]],
            "pagination": result["pagination"],
        }
    )


@shop_bp.route("/orders/stats", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_shop_order_stats():
    user = get_current_user()
    shop = _get_owner_shop(user)
    total = Order.query.filter_by(shop_id=shop.id).count()
    return success_response(
        data={
            "total": total,
            "pending": Order.query.filter_by(shop_id=shop.id, status="pending").count(),
            "confirmed": Order.query.filter_by(shop_id=shop.id, status="confirmed").count(),
            "preparing": Order.query.filter_by(shop_id=shop.id, status="preparing").count(),
            "delivered": Order.query.filter_by(shop_id=shop.id, status="delivered").count(),
            "cancelled": Order.query.filter_by(shop_id=shop.id, status="cancelled").count(),
        }
    )


@shop_bp.route("/orders/<order_id>", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_shop_order(order_id):
    user = get_current_user()
    shop = _get_owner_shop(user)
    order = Order.query.filter_by(order_number=order_id, shop_id=shop.id).first()
    if not order:
        return error_response("Order not found", 404)
    return success_response(data=order.to_dict())


@shop_bp.route("/orders/<order_id>/status", methods=["PUT", "POST"])
@jwt_required()
@require_role("shop_owner")
def update_shop_order_status(order_id):
    user = get_current_user()
    shop = _get_owner_shop(user)
    order = Order.query.filter_by(order_number=order_id, shop_id=shop.id).first()
    if not order:
        return error_response("Order not found", 404)

    data = request.get_json()
    new_status = data.get("status")

    allowed = ["confirmed", "preparing", "ready", "cancelled"]
    if new_status not in allowed:
        return error_response(f"Shop can only set status to: {', '.join(allowed)}")

    order.status = new_status
    if new_status == "cancelled":
        order.cancelled_at = datetime.utcnow()
        order.cancellation_reason = data.get("reason")

    history = OrderStatusHistory(order_id=order.id, status=new_status, changed_by=user.id)
    db.session.add(history)
    db.session.commit()

    return success_response(data=order.to_dict(), message="Order status updated")


@shop_bp.route("/orders/bulk", methods=["PUT"])
@jwt_required()
@require_role("shop_owner")
def bulk_update_shop_orders():
    user = get_current_user()
    shop = _get_owner_shop(user)
    data = request.get_json()
    order_numbers = data.get("orders", [])
    new_status = data.get("status")

    Order.query.filter(
        Order.order_number.in_(order_numbers),
        Order.shop_id == shop.id,
    ).update({"status": new_status}, synchronize_session=False)
    db.session.commit()

    return success_response(message=f"Updated {len(order_numbers)} orders")


@shop_bp.route("/wallet", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_shop_wallet():
    user = get_current_user()
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if not wallet:
        wallet = Wallet(user_id=user.id)
        db.session.add(wallet)
        db.session.commit()
    recent_txns = WalletTransaction.query.filter_by(wallet_id=wallet.id).order_by(
        desc(WalletTransaction.created_at)
    ).limit(10).all()
    return success_response(
        data={
            "balance": float(wallet.balance),
            "currency": wallet.currency,
            "recent_transactions": [t.to_dict() for t in recent_txns],
        }
    )


@shop_bp.route("/wallet/withdraw", methods=["POST"])
@jwt_required()
@require_role("shop_owner")
def withdraw_shop_earnings():
    user = get_current_user()
    data = request.get_json()
    amount = float(data.get("amount", 0))
    if amount <= 0:
        return error_response("Invalid amount")
    wallet = Wallet.query.filter_by(user_id=user.id).first()
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
        description="Shop earnings withdrawal",
        payment_method=data.get("payment_method", "mpesa"),
        status="completed",
    )
    db.session.add(txn)
    from app.models.payout import Payout
    payout = Payout(
        user_id=user.id,
        user_type="shop",
        amount=amount,
        status="pending",
        payment_method=data.get("payment_method", "mpesa"),
    )
    db.session.add(payout)
    db.session.commit()
    return success_response(data={"new_balance": float(wallet.balance)}, message="Withdrawal request submitted")


@shop_bp.route("/orders/status-flow", methods=["GET"])
@jwt_required()
@require_role("shop_owner")
def get_order_status_flow():
    return success_response(
        data={
            "flow": [
                {"status": "pending", "label": "Pending", "next": ["confirmed", "cancelled"]},
                {"status": "confirmed", "label": "Confirmed", "next": ["preparing"]},
                {"status": "preparing", "label": "Preparing", "next": ["ready"]},
                {"status": "ready", "label": "Ready", "next": ["picked_up"]},
                {"status": "picked_up", "label": "Picked Up", "next": ["in_transit"]},
                {"status": "in_transit", "label": "In Transit", "next": ["delivered"]},
                {"status": "delivered", "label": "Delivered", "next": []},
                {"status": "cancelled", "label": "Cancelled", "next": []},
            ]
        }
    )

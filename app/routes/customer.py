from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import desc, func
from app import db
from app.models.user import User
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.shop import Shop, ShopCategory, Product, Review, ProductCategory
from app.models.wallet import Wallet, WalletTransaction
from app.models.address import Address
from app.models.notification import Notification
from app.utils.helpers import (
    success_response, error_response, require_role,
    get_current_user, paginate_query, generate_order_number,
)

customer_bp = Blueprint("customer", __name__)


# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────

@customer_bp.route("/dashboard", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_customer_dashboard():
    user = get_current_user()
    recent_orders = Order.query.filter_by(customer_id=user.id).order_by(
        desc(Order.created_at)
    ).limit(5).all()
    wallet = Wallet.query.filter_by(user_id=user.id).first()

    return success_response(
        data={
            "user": user.to_dict(),
            "wallet_balance": wallet.balance if wallet else 0,
            "total_orders": Order.query.filter_by(customer_id=user.id).count(),
            "recent_orders": [o.to_dict() for o in recent_orders],
        }
    )


@customer_bp.route("/orders/recent", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_customer_recent_orders():
    user = get_current_user()    
    limit = int(request.args.get("limit", 5))
    orders = Order.query.filter_by(customer_id=user.id).order_by(
        desc(Order.created_at)
    ).limit(limit).all()
    return success_response(data={"orders": [o.to_dict() for o in orders]})


@customer_bp.route("/orders/<order_id>", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_customer_order(order_id):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_id, customer_id=user.id).first()
    if not order:
        return error_response("Order not found", 404)
    return success_response(data=order.to_dict())


# ──────────────────────────────────────────────
# PROFILE
# ──────────────────────────────────────────────

@customer_bp.route("/profile", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_customer_profile():
    user = get_current_user()
    return success_response(data=user.to_dict())


@customer_bp.route("/profile", methods=["PUT"])
@jwt_required()
@require_role("customer")
def update_customer_profile():
    user = get_current_user()
    data = request.get_json()
    if data.get("name"):
        user.name = data["name"]
    if data.get("email"):
        user.email = data["email"]
    db.session.commit()
    return success_response(data=user.to_dict(), message="Profile updated")


# ──────────────────────────────────────────────
# WALLET
# ──────────────────────────────────────────────

@customer_bp.route("/wallet", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_customer_wallet():
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
            "balance": wallet.balance,
            "currency": wallet.currency,
            "recent_transactions": [t.to_dict() for t in recent_txns],
            "total_saved": 0,
            "updated_at": wallet.updated_at
        }
    )


@customer_bp.route("/wallet/add", methods=["POST"])
@jwt_required()
@require_role("customer")
def add_money_to_wallet():
    user = get_current_user()
    data = request.get_json()
    amount = float(data.get("amount", 0))
    payment_method = data.get("payment_method", "mpesa")

    if amount <= 0:
        return error_response("Invalid amount")

    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if not wallet:
        wallet = Wallet(user_id=user.id)
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
        description=f"Wallet top-up via {payment_method}",
        payment_method=payment_method,
        status="completed",
    )
    db.session.add(txn)
    db.session.commit()
    
    recent_txns = WalletTransaction.query.filter_by(wallet_id=wallet.id).order_by(
        desc(WalletTransaction.created_at)
    ).limit(10).all()

    return success_response(
        data={"balance": wallet.balance, 
              "transaction_id": txn.id,
              "recent_transactions": [t.to_dict() for t in recent_txns],
              "total_saved": 0,
              "updated_at": wallet.updated_at,
              "currency": wallet.currency,
              },
        message="Wallet topped up successfully",
    )


@customer_bp.route("/wallet/withdraw", methods=["POST"])
@jwt_required()
@require_role("customer")
def withdraw_from_wallet():
    user = get_current_user()
    data = request.get_json()
    amount = float(data.get("amount", 0))

    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if not wallet or wallet.balance < amount:
        return error_response("Insufficient wallet balance")

    balance_before = wallet.balance
    wallet.balance -= amount

    txn = WalletTransaction(
        wallet_id=wallet.id,
        transaction_type="debit",
        amount=amount,
        balance_before=balance_before,
        balance_after=wallet.balance,
        description="Wallet withdrawal",
        payment_method=data.get("payment_method", "mpesa"),
        status="completed",
    )
    db.session.add(txn)
    db.session.commit()

    return success_response(
        data={"new_balance": wallet.balance},
        message="Withdrawal successful",
    )


@customer_bp.route("/wallet/transactions", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_wallet_transactions():
    user = get_current_user()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 20))

    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if not wallet:
        return success_response(data={"transactions": [], "pagination": {}})

    query = WalletTransaction.query.filter_by(wallet_id=wallet.id).order_by(
        desc(WalletTransaction.created_at)
    )
    result = paginate_query(query, page, per_page)

    return success_response(
        data={
            "transactions": [t.to_dict() for t in result["items"]],
            "pagination": result["pagination"],
            "balance": wallet.balance,
            "updated_at": wallet.updated_at
        }
    )


# ──────────────────────────────────────────────
# SHOPS
# ──────────────────────────────────────────────

@customer_bp.route("/shops", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_shops():
    category = request.args.get("category")
    search = request.args.get("search")
    is_open = request.args.get("isOpen")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 20))

    query = Shop.query.filter_by(status="active")

    if category:
        query = query.join(ShopCategory).filter(ShopCategory.name.ilike(f"%{category}%"))
    if search:
        query = query.filter(Shop.name.ilike(f"%{search}%"))
    if is_open == "true":
        query = query.filter_by(is_open=True)

    result = paginate_query(query, page, per_page)
    return success_response(
        data={
            "shops": [s.to_dict() for s in result["items"]],
            "pagination": result["pagination"],
        }
    )


@customer_bp.route("/shops/categories", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_shop_categories():

    categories = (
        db.session.query(
            ShopCategory,
            func.count(Shop.id).label("count")
        )
        .outerjoin(Shop, Shop.category_id == ShopCategory.id)
        .filter(ShopCategory.is_active == True)
        .group_by(ShopCategory.id)
        .order_by(ShopCategory.sort_order)
        .all()
    )

    data = []
    for category, count in categories:
        c_dict = category.to_dict()
        c_dict["count"] = count
        data.append(c_dict)

    return success_response(data={"categories": data})


@customer_bp.route("/shops/<int:shop_id>", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_shop(shop_id):
    shop = Shop.query.filter_by(id=shop_id, status="active").first()
    if not shop:
        return error_response("Shop not found", 404)
    return success_response(data=shop.to_dict())


@customer_bp.route("/shops/<int:shop_id>/categories", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_shop_product_categories(shop_id):
    from app.models.shop import ProductCategory
    categories = ProductCategory.query.filter_by(shop_id=shop_id, is_active=True).all()
    return success_response(data={"categories": [c.to_dict() for c in categories]})


@customer_bp.route("/shops/<int:shop_id>/reviews", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_shop_reviews(shop_id):
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 20))

    query = Review.query.filter_by(shop_id=shop_id).order_by(desc(Review.created_at))
    result = paginate_query(query, page, per_page)

    reviews_data = [
        {
            "id": r.id,
            "user": r.customer.name if r.customer else "Anonymous",
            "rating": r.rating,
            "comment": r.comment,
            "date": r.created_at.replace(tzinfo=timezone.utc).isoformat() if r.created_at else None,
        }
        for r in result["items"]
    ]

    return success_response(
        data={
            "reviews": reviews_data,
            "pagination": result["pagination"],
        }
    )


# ──────────────────────────────────────────────
# PRODUCTS
# ──────────────────────────────────────────────

@customer_bp.route("/products", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_customer_products():
    shop_id = request.args.get("shop_id")
    category_id = request.args.get("category_id")
    search = request.args.get("search")
    featured = request.args.get("featured")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 20))

    # --- Products query ---
    query = Product.query.filter_by(is_available=True)
    if shop_id:
        query = query.filter_by(shop_id=int(shop_id))
    if category_id:
        query = query.filter_by(category_id=int(category_id))
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if featured == "true":
        query = query.filter_by(is_featured=True)

    result = paginate_query(query, page, per_page)

    # --- Categories query ---
    categories = []
    if shop_id:
        categories_query = ProductCategory.query.filter_by(
            shop_id=int(shop_id),
            is_active=True
        ).order_by(ProductCategory.sort_order)
        categories = [c.to_dict() for c in categories_query.all()]

    return success_response(
        data={
            "products": [p.to_dict() for p in result["items"]],
            "pagination": result["pagination"],
            "categories": categories
        }
    )

# ──────────────────────────────────────────────
# ORDERS (customer)
# ──────────────────────────────────────────────

@customer_bp.route("/orders", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_orders():
    user = get_current_user()
    status = request.args.get("status")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 10))

    query = Order.query.filter_by(customer_id=user.id)
    if status and status != "all":
        query = query.filter_by(status=status)
    query = query.order_by(desc(Order.created_at))

    result = paginate_query(query, page, per_page)
    return success_response(
        data={
            "orders": [o.to_dict() for o in result["items"]],
            "pagination": result["pagination"],
        }
    )


@customer_bp.route("/orders/<order_id>/status", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_order_status(order_id):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_id, customer_id=user.id).first()
    if not order:
        return error_response("Order not found", 404)
    history = order.status_history.order_by(OrderStatusHistory.created_at).all()
    return success_response(
        data={
            "status": order.status,
            "order_number": order.order_number,
            "history": [h.to_dict() for h in history],
        }
    )


@customer_bp.route("/orders/<order_id>/track", methods=["GET"])
@jwt_required()
@require_role("customer")
def track_order(order_id):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_id, customer_id=user.id).first()
    if not order:
        return error_response("Order not found", 404)

    rider_location = None
    if order.rider_id:
        from app.models.delivery import RiderLocation
        loc = RiderLocation.query.filter_by(rider_id=order.rider_id).first()
        if loc:
            rider_location = loc.to_dict()

    return success_response(
        data={
            "order": order.to_dict(),
            "rider_location": rider_location,
        }
    )


@customer_bp.route("/orders/<order_id>/cancel", methods=["POST"])
@jwt_required()
@require_role("customer")
def cancel_order(order_id):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_id, customer_id=user.id).first()
    if not order:
        return error_response("Order not found", 404)

    if order.status not in ("pending", "confirmed"):
        return error_response("Order cannot be cancelled at this stage")

    data = request.get_json() or {}
    order.status = "cancelled"
    order.cancelled_at = datetime.utcnow()
    order.cancellation_reason = data.get("reason", "Cancelled by customer")

    history = OrderStatusHistory(order_id=order.id, status="cancelled", changed_by=user.id)
    db.session.add(history)
    db.session.commit()

    return success_response(message="Order cancelled")


@customer_bp.route("/orders/<order_id>/reorder", methods=["POST"])
@jwt_required()
@require_role("customer")
def reorder(order_id):
    user = get_current_user()
    original = Order.query.filter_by(order_number=order_id, customer_id=user.id).first()
    if not original:
        return error_response("Order not found", 404)

    new_order = Order(
        order_number=generate_order_number(),
        customer_id=user.id,
        shop_id=original.shop_id,
        subtotal=original.subtotal,
        delivery_fee=original.delivery_fee,
        total_amount=original.total_amount,
        payment_method=original.payment_method,
        delivery_address_text=original.delivery_address_text,
        notes=original.notes,
        status="pending",
    )
    db.session.add(new_order)
    db.session.flush()

    for item in original.items:
        new_item = OrderItem(
            order_id=new_order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.total_price,
        )
        db.session.add(new_item)

    db.session.commit()
    return success_response(data=new_order.to_dict(), message="Reorder placed successfully", status_code=201)


@customer_bp.route("/orders/<order_id>/rate", methods=["POST"])
@jwt_required()
@require_role("customer")
def rate_order(order_id):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_id, customer_id=user.id).first()
    if not order:
        return error_response("Order not found", 404)
    if order.status != "delivered":
        return error_response("Can only rate delivered orders")

    data = request.get_json()
    order.rating = data.get("rating")
    order.review = data.get("review")

    # Create shop review
    from app.utils.helpers import update_shop_rating
    review = Review(
        shop_id=order.shop_id,
        customer_id=user.id,
        order_id=order.id,
        rating=data.get("rating"),
        comment=data.get("review"),
        is_verified=True,
    )
    db.session.add(review)
    db.session.commit()
    update_shop_rating(order.shop)

    return success_response(message="Rating submitted successfully")


@customer_bp.route("/orders/<order_id>/support", methods=["POST"])
@jwt_required()
@require_role("customer")
def contact_order_support(order_id):
    # In production, create a support ticket or send an email
    data = request.get_json()
    return success_response(
        data={"ticket_id": f"TKT-{order_id[-4:]}"},
        message="Support request submitted. We'll reach out shortly.",
    )


# ──────────────────────────────────────────────
# ADDRESSES
# ──────────────────────────────────────────────

@customer_bp.route("/addresses", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_addresses():
    user = get_current_user()
    addresses = Address.query.filter_by(user_id=user.id).all()
    return success_response(data={"addresses": [a.to_dict() for a in addresses]})


@customer_bp.route("/addresses/<int:address_id>", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_address(address_id):
    user = get_current_user()
    addr = Address.query.filter_by(id=address_id, user_id=user.id).first()
    if not addr:
        return error_response("Address not found", 404)
    return success_response(data=addr.to_dict())


@customer_bp.route("/addresses", methods=["POST"])
@jwt_required()
@require_role("customer")
def add_address():
    user = get_current_user()
    data = request.get_json()

    if data.get("is_default"):
        Address.query.filter_by(user_id=user.id).update({"is_default": False})

    addr = Address(
        user_id=user.id,
        label=data.get("label"),
        street=data.get("street", ""),
        city=data.get("city"),
        area=data.get("area"),
        building=data.get("building"),
        floor=data.get("floor"),
        door=data.get("door"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        notes=data.get("notes"),
        is_default=data.get("is_default", False),
    )
    db.session.add(addr)
    db.session.commit()
    return success_response(data=addr.to_dict(), message="Address added", status_code=201)


@customer_bp.route("/addresses/<int:address_id>", methods=["PUT"])
@jwt_required()
@require_role("customer")
def update_address(address_id):
    user = get_current_user()
    addr = Address.query.filter_by(id=address_id, user_id=user.id).first()
    if not addr:
        return error_response("Address not found", 404)

    data = request.get_json()
    for field in ("label", "street", "city", "area", "building", "floor", "door", "notes", "latitude", "longitude"):
        if field in data:
            setattr(addr, field, data[field])

    db.session.commit()
    return success_response(data=addr.to_dict(), message="Address updated")


@customer_bp.route("/addresses/<int:address_id>", methods=["DELETE"])
@jwt_required()
@require_role("customer")
def delete_address(address_id):
    user = get_current_user()
    addr = Address.query.filter_by(id=address_id, user_id=user.id).first()
    if not addr:
        return error_response("Address not found", 404)
    db.session.delete(addr)
    db.session.commit()
    return success_response(message="Address deleted")


@customer_bp.route("/addresses/<int:address_id>/default", methods=["PUT"])
@jwt_required()
@require_role("customer")
def set_default_address(address_id):
    user = get_current_user()
    Address.query.filter_by(user_id=user.id).update({"is_default": False})
    addr = Address.query.filter_by(id=address_id, user_id=user.id).first()
    if not addr:
        return error_response("Address not found", 404)
    addr.is_default = True
    db.session.commit()
    return success_response(message="Default address set")


@customer_bp.route("/addresses/validate", methods=["POST"])
@jwt_required()
@require_role("customer")
def validate_address():
    data = request.get_json()
    address = data.get("address", "")
    # In production, integrate with Google Maps / geocoding API
    return success_response(
        data={"is_valid": bool(address), "formatted_address": address},
        message="Address validated",
    )


# ──────────────────────────────────────────────
# CHECKOUT
# ──────────────────────────────────────────────

@customer_bp.route("/checkout", methods=["GET"])
@jwt_required()
@require_role("customer")
def get_checkout_data():
    user = get_current_user()
    shop_id = request.args.get("shop")
    shop = Shop.query.filter_by(id=shop_id, status="active").first() if shop_id else None
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    addresses = Address.query.filter_by(user_id=user.id).all()

    addresses_data = []
    for a in addresses:
        addresses_data.append({
            "id": a.id,
            "label": a.label,
            "address": f"{a.street}, {a.area}, {a.city}" if a.area or a.city else a.street,
            "address_line2": f"{a.building}, Floor {a.floor}, Door {a.door}".strip(", "),
            "landmark": a.notes or "",
            "phone": user.phone if hasattr(user, "phone") else "",  # assuming User has phone
            "is_default": a.is_default,
            "lat": a.latitude,
            "lng": a.longitude,
            "created_at": a.created_at.replace(tzinfo=timezone.utc).isoformat() if a.created_at else None,
            "updated_at": a.updated_at.replace(tzinfo=timezone.utc).isoformat() if a.updated_at else None,
            "delivery_instructions": a.notes or "",
        })
        
    payment_methods = [
        {
            "id": "mpesa",
            "name": "M-Pesa",
            "icon": "Smartphone",
            "description": "Pay instantly with M-Pesa"
        },
        {
            "id": "card",
            "name": "Credit/Debit Card",
            "icon": "CreditCard",
            "description": "Pay with Visa, Mastercard, or American Express"
        }
    ]

    return success_response(
        data={
            "shop": shop.to_dict() if shop else None,
            "wallet_balance": wallet.balance if wallet else 0,
            "addresses": addresses_data,
            "payment_methods": payment_methods,
        }
    )


@customer_bp.route("/orders", methods=["POST"])
@jwt_required()
@require_role("customer")
def place_order():
    user = get_current_user()
    data = request.get_json()

    shop = Shop.query.get(data.get("shop_id"))
    if not shop:
        return error_response("Shop not found", 404)

    items = data.get("items", [])
    if not items:
        return error_response("Order must have at least one item")

    subtotal = 0
    order_items_data = []
    for item_data in items:
        product = Product.query.get(item_data["product_id"])
        if not product or not product.is_available:
            return error_response(f"Product {item_data.get('product_id')} is not available")
        qty = item_data.get("quantity", 1)
        total = product.price * qty
        subtotal += total
        order_items_data.append((product, qty, product.price, total))

    delivery_fee = shop.delivery_fee
    discount = 0
    coupon_code = data.get("coupon_code")
    # Coupon validation logic can be expanded here

    total_amount = subtotal + delivery_fee - discount

    # Payment via wallet
    payment_method = data.get("payment_method", "mpesa")
    if payment_method == "wallet":
        wallet = Wallet.query.filter_by(user_id=user.id).first()
        if not wallet or wallet.balance < total_amount:
            return error_response("Insufficient wallet balance")
        wallet.balance -= total_amount
        wallet_txn = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type="debit",
            amount=total_amount,
            balance_before=wallet.balance + total_amount,
            balance_after=wallet.balance,
            description=f"Order payment",
            status="completed",
        )
        db.session.add(wallet_txn)

    wallet_paid = payment_method == "wallet"
    initial_status = "confirmed" if wallet_paid else "pending"

    order = Order(
        order_number=generate_order_number(),
        customer_id=user.id,
        shop_id=shop.id,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        discount=discount,
        total_amount=total_amount,
        payment_method=payment_method,
        payment_status="paid" if wallet_paid else "pending",
        delivery_address_id=data.get("delivery_address_id"),
        delivery_address_text=data.get("delivery_address"),
        notes=data.get("notes"),
        coupon_code=coupon_code,
        status=initial_status,
    )
    db.session.add(order)
    db.session.flush()

    for product, qty, unit_price, total in order_items_data:
        item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=qty,
            unit_price=unit_price,
            total_price=total,
        )
        db.session.add(item)
        product.total_orders += 1

    history = OrderStatusHistory(order_id=order.id, status="pending", changed_by=user.id)
    db.session.add(history)
    if wallet_paid:
        db.session.add(OrderStatusHistory(order_id=order.id, status="confirmed", changed_by=user.id))

    shop.total_orders += 1
    db.session.commit()

    return success_response(data=order.to_dict(), message="Order placed successfully", status_code=201)


@customer_bp.route("/orders/<order_id>/pay", methods=["POST"])
@jwt_required()
@require_role("customer")
def pay_order(order_id):
    user = get_current_user()
    order = Order.query.filter_by(order_number=order_id, customer_id=user.id).first()
    if not order:
        return error_response("Order not found", 404)
    if order.payment_status == "paid":
        return error_response("Order is already paid")

    data = request.get_json() or {}
    payment_method = data.get("payment_method", order.payment_method or "mpesa")

    if payment_method == "wallet":
        wallet = Wallet.query.filter_by(user_id=user.id).first()
        if not wallet or wallet.balance < order.total_amount:
            return error_response("Insufficient wallet balance")
        balance_before = wallet.balance
        wallet.balance -= order.total_amount
        txn = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type="debit",
            amount=order.total_amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            description=f"Payment for order {order.order_number}",
            status="completed",
        )
        db.session.add(txn)
        order.payment_status = "paid"
        order.payment_method = "wallet"
    else:
        # Simulate M-Pesa / card success (no real webhook in dev)
        order.payment_method = payment_method
        order.payment_status = "paid"
        if order.status == "pending":
            order.status = "confirmed"
            db.session.add(OrderStatusHistory(order_id=order.id, status="confirmed", changed_by=user.id))

    db.session.commit()
    return success_response(
        data={
            "order_number": order.order_number,
            "payment_status": order.payment_status,
            "payment_method": order.payment_method,
            "amount": float(order.total_amount),
            "transaction_id": f"TXN-{order.order_number}",
        },
        message="Payment processed successfully",
    )


@customer_bp.route("/coupons/validate", methods=["POST"])
@jwt_required()
@require_role("customer")
def validate_coupon():
    data = request.get_json()
    coupon_code = data.get("couponCode", "")
    # In production, look up coupon in database
    # For now return a simple validation response
    valid_coupons = {"WELCOME10": 10, "SAVE20": 20}
    discount = valid_coupons.get(coupon_code.upper())
    if discount:
        return success_response(
            data={"valid": True, "discount_percent": discount, "code": coupon_code}
        )
    return error_response("Invalid or expired coupon code")


# Add this temporarily to your customer.py or a new debug route

@customer_bp.route("/debug/verify-token", methods=["GET"])
@jwt_required(optional=True)  # This won't fail if token is invalid
def verify_token_debug():
    """Debug endpoint to check token validity"""
    from flask import request
    from flask_jwt_extended import decode_token, get_jwt
    
    auth_header = request.headers.get('Authorization', '')
    print(f"Auth header: {auth_header}")
    
    if not auth_header.startswith('Bearer '):
        return jsonify({
            "error": "Invalid authorization header format",
            "success": False
        }), 400
    
    token = auth_header.split(' ')[1]
    print(f"Token: {token[:20]}...")  # Print first 20 chars only
    
    try:
        # Try to decode the token
        decoded = decode_token(token)
        print(f"Decoded token: {decoded}")
        
        # Get user from token
        user_id = decoded['sub']
        user = User.query.get(user_id)
        
        return jsonify({
            "success": True,
            "data": {
                "token_valid": True,
                "user_id": user_id,
                "user_exists": user is not None,
                "user_role": user.role if user else None,
                "token_type": decoded.get('type'),
                "expires": decoded.get('exp')
            }
        }), 200
        
    except Exception as e:
        print(f"Token decode error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "token_valid": False
        }), 401
from datetime import datetime
from app import db
from app.models.address import Address


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    rider_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    delivery_address_id = db.Column(db.Integer, db.ForeignKey("addresses.id"), nullable=True)
    delivery_address_text = db.Column(db.String(500), nullable=True)
    subtotal = db.Column(db.Float, nullable=False)
    delivery_fee = db.Column(db.Float, default=0)
    discount = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(
        db.Enum("pending", "paid", "failed", "refunded", name="payment_status"),
        default="pending",
    )
    payment_reference = db.Column(db.String(200), nullable=True)
    status = db.Column(
        db.Enum(
            "pending", "confirmed", "preparing", "ready",
            "picked_up", "in_transit", "delivered", "cancelled",
            name="order_status",
        ),
        default="pending",
    )
    notes = db.Column(db.Text, nullable=True)
    coupon_code = db.Column(db.String(50), nullable=True)
    rating = db.Column(db.Float, nullable=True)
    review = db.Column(db.Text, nullable=True)
    estimated_delivery_time = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = db.relationship("User", foreign_keys=[customer_id], back_populates="orders")
    rider = db.relationship("User", foreign_keys=[rider_id])
    shop = db.relationship("Shop", back_populates="orders")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    status_history = db.relationship("OrderStatusHistory", back_populates="order", lazy="dynamic")
    delivery = db.relationship("Delivery", back_populates="order", uselist=False)

    def to_dict(self, include_items=True):
        delivery_address = None
        if self.delivery_address_id:
            addr = Address.query.get(self.delivery_address_id)
            if addr:
                parts = [
                    addr.street,
                    addr.building,
                    addr.area,
                    addr.city,
                ]
                delivery_address = ", ".join([str(p) for p in parts if p])
        
        data = {
            "id": self.order_number,
            "db_id": self.id,
            "customer": {
                "id": self.customer_id,
                "name": self.customer.name if self.customer else None,
                "email": self.customer.email if self.customer else None,
                "phone": self.customer.phone if self.customer else None,
            },
            "shop": {
                "id": self.shop_id,
                "name": self.shop.name if self.shop else None,
                "phone": self.shop.phone if self.shop else None,
                "address": self.shop.address if self.shop else None,
            },
            "rider": {
                "id": self.rider_id,
                "name": self.rider.name if self.rider else None,
                "phone": self.rider.phone if self.rider else None,
            } if self.rider_id else None,
            "subtotal": self.subtotal,
            "delivery_fee": self.delivery_fee,
            "discount": self.discount,
            "total_amount": self.total_amount,
            "payment_method": self.payment_method,
            "payment_status": self.payment_status,
            "status": self.status,
            "notes": self.notes,
            "rating": self.rating,
            "review": self.review,
            "delivery_address": delivery_address,
            "estimated_delivery_time": self.estimated_delivery_time.isoformat() if self.estimated_delivery_time else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_items:
            data["items"] = [item.to_dict() for item in self.items]
        return data


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product", back_populates="order_items")

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "name": self.product.name if self.product else None,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "total_price": self.total_price,
            "notes": self.notes,
        }


class OrderStatusHistory(db.Model):
    __tablename__ = "order_status_history"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    note = db.Column(db.Text, nullable=True)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship("Order", back_populates="status_history")

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

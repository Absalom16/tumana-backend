from datetime import datetime
from app import db


class Delivery(db.Model):
    __tablename__ = "deliveries"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, unique=True)
    rider_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(
        db.Enum(
            "unassigned", "assigned", "picked_up", "in_transit",
            "delivered", "cancelled", name="delivery_status",
        ),
        default="unassigned",
    )
    pickup_latitude = db.Column(db.Float, nullable=True)
    pickup_longitude = db.Column(db.Float, nullable=True)
    dropoff_latitude = db.Column(db.Float, nullable=True)
    dropoff_longitude = db.Column(db.Float, nullable=True)
    distance_km = db.Column(db.Float, nullable=True)
    delivery_fee = db.Column(db.Float, nullable=True)
    rider_earnings = db.Column(db.Float, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    picked_up_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = db.relationship("Order", back_populates="delivery")
    rider = db.relationship("User", foreign_keys=[rider_id])

    def to_dict(self):
        order = self.order
        customer = order.customer if order else None
        shop = order.shop if order else None

        delivery_address = None
        if order and order.delivery_address_id:
            from app.models.address import Address
            addr = Address.query.get(order.delivery_address_id)
            if addr:
                parts = [addr.street, addr.building, addr.area, addr.city]
                delivery_address = ", ".join(p for p in parts if p)
        delivery_address = (
            delivery_address
            or (order.delivery_address_text if order else None)
            or "N/A"
        )

        status_progress = {
            "unassigned": 0,
            "assigned": 10,
            "picked_up": 50,
            "in_transit": 75,
            "delivered": 100,
            "cancelled": 0,
        }
        location_label = {
            "assigned": "Heading to shop",
            "picked_up": "Order picked up",
            "in_transit": "En route to customer",
            "delivered": "Delivered",
            "cancelled": "Cancelled",
        }

        return {
            "id": self.id,
            "order_id": order.order_number if order else self.order_id,
            "order_number": order.order_number if order else None,
            "rider_id": self.rider_id,
            "status": self.status,
            "shop_name": shop.name if shop else "Unknown Shop",
            "shop_address": shop.address if shop else "N/A",
            "customer_name": customer.name if customer else "Unknown Customer",
            "customer_phone": customer.phone if customer else None,
            "delivery_address": delivery_address,
            "distance_km": self.distance_km,
            "distance": f"{self.distance_km:.1f} km" if self.distance_km else "N/A",
            "delivery_fee": self.delivery_fee,
            "rider_earnings": self.rider_earnings,
            "earnings": self.rider_earnings or 0,
            "total_amount": float(order.total_amount) if order else 0,
            "progress": status_progress.get(self.status, 0),
            "current_location": location_label.get(self.status, "Unknown"),
            "route": [],
            "urgency": "normal",
            "notes": self.notes or (order.notes if order else None),
            "items_count": len(order.items) if order else 0,
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "picked_up_at": self.picked_up_at.isoformat() if self.picked_up_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RiderLocation(db.Model):
    __tablename__ = "rider_locations"

    id = db.Column(db.Integer, primary_key=True)
    rider_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    is_online = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rider = db.relationship("User")

    def to_dict(self):
        return {
            "rider_id": self.rider_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "is_online": self.is_online,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

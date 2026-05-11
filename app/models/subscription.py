from datetime import datetime
from app import db


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    plan_name = db.Column(db.String(100), nullable=False)
    plan_type = db.Column(db.Enum("basic", "standard", "premium", name="plan_type"), default="basic")
    status = db.Column(
        db.Enum("active", "inactive", "cancelled", "expired", "trial", name="sub_status"),
        default="trial",
    )
    amount = db.Column(db.Float, nullable=False)
    billing_cycle = db.Column(db.Enum("monthly", "yearly", name="billing_cycle"), default="monthly")
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    auto_renew = db.Column(db.Boolean, default=True)
    payment_method = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shop = db.relationship("Shop")

    def to_dict(self):
        return {
            "id": self.id,
            "shop_id": self.shop_id,
            "plan_name": self.plan_name,
            "plan_type": self.plan_type,
            "status": self.status,
            "amount": self.amount,
            "billing_cycle": self.billing_cycle,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "auto_renew": self.auto_renew,
            "payment_method": self.payment_method,
            "shop": {"id": self.shop.id, "name": self.shop.name} if self.shop else None,
        }

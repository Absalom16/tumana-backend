from datetime import datetime
from app import db


class Payout(db.Model):
    __tablename__ = "payouts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user_type = db.Column(db.Enum("rider", "shop", name="payout_user_type"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(
        db.Enum("pending", "processing", "completed", "failed", name="payout_status"),
        default="pending",
    )
    payment_method = db.Column(db.String(50), nullable=True)
    payment_reference = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    processed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_type": self.user_type,
            "amount": self.amount,
            "status": self.status,
            "payment_method": self.payment_method,
            "payment_reference": self.payment_reference,
            "notes": self.notes,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

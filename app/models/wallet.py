from datetime import datetime
from app import db


class Wallet(db.Model):
    __tablename__ = "wallets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    balance = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(10), default="KES")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", back_populates="wallet")
    transactions = db.relationship("WalletTransaction", back_populates="wallet", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "balance": self.balance,
            "currency": self.currency,
            "is_active": self.is_active,
            "updated_at": self.updated_at
        }


class WalletTransaction(db.Model):
    __tablename__ = "wallet_transactions"

    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey("wallets.id"), nullable=False)
    transaction_type = db.Column(
        db.Enum("credit", "debit", name="transaction_type"),
        nullable=False,
    )
    amount = db.Column(db.Float, nullable=False)
    balance_before = db.Column(db.Float, nullable=False)
    balance_after = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(300), nullable=True)
    reference = db.Column(db.String(200), nullable=True)
    status = db.Column(
        db.Enum("pending", "completed", "failed", name="txn_status"),
        default="completed",
    )
    payment_method = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    wallet = db.relationship("Wallet", back_populates="transactions")

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.transaction_type,
            "amount": self.amount,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "description": self.description,
            "reference": self.reference,
            "status": self.status,
            "payment_method": self.payment_method,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

from datetime import datetime
from app import db, bcrypt


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    pin_hash = db.Column(db.String(255), nullable=True)
    fingerprint_template = db.Column(db.Text, nullable=True)
    id_number = db.Column(db.String(50), nullable=True)
    role = db.Column(
        db.Enum("admin", "customer", "rider", "shop_owner", name="user_roles"),
        nullable=False,
        default="customer",
    )
    status = db.Column(
        db.Enum("active", "inactive", "suspended", "pending", name="user_status"),
        default="pending",
    )
    is_verified = db.Column(db.Boolean, default=False)
    avatar_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # Relationships
    addresses = db.relationship("Address", back_populates="user", lazy="dynamic")
    wallet = db.relationship("Wallet", back_populates="user", uselist=False)
    orders = db.relationship("Order", foreign_keys="Order.customer_id", back_populates="customer", lazy="dynamic")
    notifications = db.relationship("Notification", back_populates="user", lazy="dynamic")
    shop = db.relationship("Shop", back_populates="owner", uselist=False)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        if not self.password_hash:
            return False
        return bcrypt.check_password_hash(self.password_hash, password)

    def set_pin(self, pin):
        self.pin_hash = bcrypt.generate_password_hash(pin).decode("utf-8")

    def check_pin(self, pin):
        if not self.pin_hash:
            return False
        return bcrypt.check_password_hash(self.pin_hash, pin)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "status": self.status,
            "is_verified": self.is_verified,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<User {self.phone} ({self.role})>"


class OTPRecord(db.Model):
    __tablename__ = "otp_records"

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    otp_code = db.Column(db.String(10), nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_valid(self):
        return not self.is_used and datetime.utcnow() < self.expires_at

    def __repr__(self):
        return f"<OTPRecord {self.phone}>"

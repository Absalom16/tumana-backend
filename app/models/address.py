from datetime import datetime
from app import db


class Address(db.Model):
    __tablename__ = "addresses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    label = db.Column(db.String(50), nullable=True)  # home, work, other
    street = db.Column(db.String(300), nullable=False)
    city = db.Column(db.String(100), nullable=True)
    area = db.Column(db.String(100), nullable=True)
    building = db.Column(db.String(200), nullable=True)
    floor = db.Column(db.String(50), nullable=True)
    door = db.Column(db.String(50), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_default = db.Column(db.Boolean, default=False)
    is_validated = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", back_populates="addresses")

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "street": self.street,
            "city": self.city,
            "area": self.area,
            "building": self.building,
            "floor": self.floor,
            "door": self.door,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "notes": self.notes,
            "is_default": self.is_default,
            "is_validated": self.is_validated,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

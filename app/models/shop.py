from datetime import datetime
from app import db


class ShopCategory(db.Model):
    __tablename__ = "shop_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shops = db.relationship("Shop", back_populates="category", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "is_active": self.is_active,
        }


class Shop(db.Model):
    __tablename__ = "shops"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("shop_categories.id"), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    address = db.Column(db.String(500), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(150), nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)
    cover_image_url = db.Column(db.String(500), nullable=True)
    status = db.Column(
        db.Enum("active", "inactive", "suspended", "pending", name="shop_status"),
        default="pending",
    )
    is_open = db.Column(db.Boolean, default=True)
    opening_time = db.Column(db.String(10), nullable=True)
    closing_time = db.Column(db.String(10), nullable=True)
    min_order_amount = db.Column(db.Float, default=0)
    delivery_fee = db.Column(db.Float, default=0)
    avg_delivery_time = db.Column(db.Integer, default=30)  # minutes
    rating = db.Column(db.Float, default=0.0)
    total_reviews = db.Column(db.Integer, default=0)
    total_orders = db.Column(db.Integer, default=0)
    commission_rate = db.Column(db.Float, default=10.0)  # percentage
    subscription_plan = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = db.relationship("User", back_populates="shop")
    category = db.relationship("ShopCategory", back_populates="shops")
    products = db.relationship("Product", back_populates="shop", lazy="dynamic")
    orders = db.relationship("Order", back_populates="shop", lazy="dynamic")
    reviews = db.relationship("Review", back_populates="shop", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "phone": self.phone,
            "email": self.email,
            "logo_url": self.logo_url,
            "cover_image_url": self.cover_image_url,
            "status": self.status,
            "is_open": self.is_open,
            "opening_time": self.opening_time,
            "closing_time": self.closing_time,
            "min_order_amount": self.min_order_amount,
            "delivery_fee": self.delivery_fee,
            "avg_delivery_time": self.avg_delivery_time,
            "rating": self.rating,
            "total_reviews": self.total_reviews,
            "total_orders": self.total_orders,
            "category": self.category.to_dict() if self.category else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ProductCategory(db.Model):
    __tablename__ = "product_categories"

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shop = db.relationship("Shop")
    products = db.relationship("Product", back_populates="category", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "shop_id": self.shop_id,
            "name": self.name,
            "description": self.description,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("product_categories.id"), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    preparation_time = db.Column(db.Integer, default=15)  # minutes
    tags = db.Column(db.JSON, nullable=True)
    total_orders = db.Column(db.Integer, default=0)
    rating = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    shop = db.relationship("Shop", back_populates="products")
    category = db.relationship("ProductCategory", back_populates="products")
    order_items = db.relationship("OrderItem", back_populates="product", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "shop_id": self.shop_id,
            "category_id": self.category_id,
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "image_url": self.image_url,
            "is_available": self.is_available,
            "is_featured": self.is_featured,
            "preparation_time": self.preparation_time,
            "tags": self.tags,
            "total_orders": self.total_orders,
            "rating": self.rating,
            "category": self.category.to_dict() if self.category else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True)
    rating = db.Column(db.Float, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shop = db.relationship("Shop", back_populates="reviews")
    customer = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "shop_id": self.shop_id,
            "customer_id": self.customer_id,
            "order_id": self.order_id,
            "rating": self.rating,
            "comment": self.comment,
            "is_verified": self.is_verified,
            "customer_name": self.customer.name if self.customer else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

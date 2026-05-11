"""
Seed script: creates the database tables and inserts a default admin user.
Run this AFTER running: flask db upgrade

Usage:
    python seed.py
"""
import os
from app import create_app, db, bcrypt
from app.models.user import User
from app.models.wallet import Wallet

app = create_app(os.environ.get("FLASK_ENV", "development"))


def seed():
    with app.app_context():
        db.create_all()
        print("✅ Tables created.")

        # Create default admin
        if not User.query.filter_by(email="admin@tumana.co.ke").first():
            admin = User(
                name="Super Admin",
                email="admin@tumana.co.ke",
                phone="+254700000000",
                role="admin",
                status="active",
                is_verified=True,
            )
            admin.set_password("Admin@1234")
            db.session.add(admin)
            db.session.flush()

            wallet = Wallet(user_id=admin.id)
            db.session.add(wallet)
            db.session.commit()
            print("✅ Admin user created: admin@tumana.co.ke / Admin@1234")
        else:
            print("ℹ️  Admin user already exists.")

        print("✅ Seeding complete.")


if __name__ == "__main__":
    seed()

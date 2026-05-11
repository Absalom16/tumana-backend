"""
Auto-initialize the database on app startup:
  1. CREATE DATABASE IF NOT EXISTS
  2. CREATE all tables (db.create_all)
  3. Seed default data for every table if empty
"""

import re
import time
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)


# ── Step 1: ensure the MySQL database itself exists ──────────────────────────

def ensure_database_exists(database_url: str) -> None:
    """
    Connect to MySQL without specifying a database and run
    CREATE DATABASE IF NOT EXISTS.  Silently skips on any error
    (e.g. insufficient privileges — the DB already exists in that case).
    """
    if not database_url or not database_url.startswith("mysql"):
        return  # SQLite / tests — nothing to do

    match = re.match(r"^(mysql\+\w+://[^/]+)/([^?]+)", database_url)
    if not match:
        log.warning("Could not parse DATABASE_URL to auto-create DB.")
        return

    base_url = match.group(1)
    db_name = match.group(2)

    import sqlalchemy
    from sqlalchemy import text

    engine = sqlalchemy.create_engine(
        base_url + "/",
        connect_args={"connect_timeout": 5},
    )

    last_exc = None
    for attempt in range(1, 13):  # up to ~60 s
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                ))
            engine.dispose()
            log.info("Database '%s' ready.", db_name)
            return
        except Exception as exc:
            last_exc = exc
            log.info("DB not ready yet (attempt %d/12): %s", attempt, exc)
            time.sleep(5)

    engine.dispose()
    log.warning("Could not auto-create database after 12 attempts: %s", last_exc)


# ── Step 2 + 3: create tables then seed ─────────────────────────────────────

def init_db(app, db) -> None:
    """Call inside create_app() after all blueprints are registered."""
    from app import bcrypt

    with app.app_context():
        # Ensure every model is imported so SQLAlchemy knows about the tables
        _import_all_models()

        # Create tables that don't exist yet
        db.create_all()
        log.info("All tables verified / created.")

        # Seed only if the users table is empty
        from app.models.user import User
        if User.query.count() == 0:
            _seed(db, bcrypt)
            log.info("Seed data inserted successfully.")
        else:
            log.info("Database already has data — skipping seed.")


def _import_all_models():
    """Import every model module so SQLAlchemy registers the metadata."""
    import app.models.user          # noqa: F401
    import app.models.shop          # noqa: F401
    import app.models.order         # noqa: F401
    import app.models.delivery      # noqa: F401
    import app.models.wallet        # noqa: F401
    import app.models.address       # noqa: F401
    import app.models.notification  # noqa: F401
    import app.models.subscription  # noqa: F401
    import app.models.payout        # noqa: F401


# ── Seed helpers ─────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed(db, bcrypt):
    from app.models.user import User
    from app.models.shop import ShopCategory, Shop, ProductCategory, Product
    from app.models.wallet import Wallet, WalletTransaction
    from app.models.address import Address
    from app.models.delivery import RiderLocation
    from app.models.notification import Notification
    from app.models.subscription import Subscription

    # ── Users ─────────────────────────────────────────────────────────────
    # Passwords hashed with bcrypt (cost 12)
    def make_user(name, email, phone, password, role, id_number,
                  status="active", verified=True):
        u = User(
            name=name,
            email=email,
            phone=phone,
            id_number=id_number,
            role=role,
            status=status,
            is_verified=verified,
            created_at=_now(),
            updated_at=_now(),
        )
        u.set_password(password)
        return u

    admin    = make_user("Tumana Admin",      "admin@tumana.co.ke",         "+254700000000", "Admin@1234",    "admin",      "00000000")
    sarah    = make_user("Sarah Muthoni",     "sarah.muthoni@gmail.com",    "+254711000001", "Customer@1234", "customer",   "30123456")
    james    = make_user("James Kariuki",     "james.kariuki@gmail.com",    "+254711000002", "Customer@1234", "customer",   "30654321")
    shop1_u  = make_user("Mama Mboga",        "shop.mboga@tumana.co.ke",    "+254722000001", "ShopOwner@1234","shop_owner", "20111111")
    shop2_u  = make_user("Java House Mgr",   "shop.java@tumana.co.ke",     "+254722000002", "ShopOwner@1234","shop_owner", "20222222")
    rider1   = make_user("Moses Kiplagat",    "rider.moses@tumana.co.ke",   "+254733000001", "Rider@1234",   "rider",      "40111111")
    rider2   = make_user("John Mutua",        "rider.john@tumana.co.ke",    "+254733000002", "Rider@1234",   "rider",      "40222222")

    all_users = [admin, sarah, james, shop1_u, shop2_u, rider1, rider2]
    for u in all_users:
        db.session.add(u)
    db.session.flush()  # populate .id without committing

    # ── Wallets ────────────────────────────────────────────────────────────
    wallet_balances = {
        admin.id:   0.0,
        sarah.id:   5000.0,
        james.id:   3200.0,
        shop1_u.id: 28500.0,
        shop2_u.id: 47200.0,
        rider1.id:  4800.0,
        rider2.id:  3150.0,
    }
    wallets = {}
    for uid, balance in wallet_balances.items():
        w = Wallet(user_id=uid, balance=balance, currency="KES", is_active=True,
                   created_at=_now(), updated_at=_now())
        db.session.add(w)
        wallets[uid] = w
    db.session.flush()

    # Seed a couple of wallet transactions for the customers so history shows
    for uid, desc, amount in [
        (sarah.id, "M-Pesa top-up",  5000.0),
        (james.id, "M-Pesa top-up",  3200.0),
        (shop1_u.id, "Order payment received", 28500.0),
        (shop2_u.id, "Order payment received", 47200.0),
        (rider1.id,  "Delivery earnings",       4800.0),
        (rider2.id,  "Delivery earnings",       3150.0),
    ]:
        w = wallets[uid]
        txn = WalletTransaction(
            wallet_id=w.id,
            transaction_type="credit",
            amount=amount,
            balance_before=0.0,
            balance_after=amount,
            description=desc,
            status="completed",
            payment_method="mpesa",
            created_at=_now(),
        )
        db.session.add(txn)

    # ── Shop Categories ────────────────────────────────────────────────────
    cat_data = [
        ("Food & Restaurants", "🍔", "Restaurants, fast food, home-cooked meals", 1),
        ("Groceries",          "🛒", "Supermarkets, fresh produce, staples",       2),
        ("Pharmacy & Health",  "💊", "Medicines, vitamins, health products",       3),
        ("Beverages",          "☕", "Juices, coffee, water, soft drinks",         4),
        ("Electronics",        "📱", "Phones, accessories, gadgets",               5),
        ("Fashion",            "👕", "Clothing, shoes, accessories",               6),
    ]
    cats = {}
    for name, icon, desc, sort in cat_data:
        c = ShopCategory(name=name, icon=icon, description=desc,
                         is_active=True, sort_order=sort, created_at=_now())
        db.session.add(c)
        cats[name] = c
    db.session.flush()

    # ── Shops ──────────────────────────────────────────────────────────────
    shop1 = Shop(
        owner_id=shop1_u.id,
        category_id=cats["Groceries"].id,
        name="Mama Mboga Fresh Market",
        description="Your neighbourhood fresh market. Delivered fast.",
        address="Westlands Square, Westlands, Nairobi",
        latitude=-1.2680,
        longitude=36.8086,
        phone="+254722000001",
        email="shop.mboga@tumana.co.ke",
        status="active",
        is_open=True,
        opening_time="07:00",
        closing_time="21:00",
        min_order_amount=200.0,
        delivery_fee=80.0,
        avg_delivery_time=25,
        rating=4.7,
        total_reviews=143,
        total_orders=892,
        commission_rate=10.0,
        subscription_plan="standard",
        created_at=_now(),
        updated_at=_now(),
    )
    shop2 = Shop(
        owner_id=shop2_u.id,
        category_id=cats["Food & Restaurants"].id,
        name="Java House Nairobi CBD",
        description="Kenya's favourite coffee shop. Great food, great vibes.",
        address="Kimathi Street, CBD, Nairobi",
        latitude=-1.2832,
        longitude=36.8167,
        phone="+254722000002",
        email="shop.java@tumana.co.ke",
        status="active",
        is_open=True,
        opening_time="06:30",
        closing_time="22:00",
        min_order_amount=350.0,
        delivery_fee=100.0,
        avg_delivery_time=35,
        rating=4.8,
        total_reviews=521,
        total_orders=2340,
        commission_rate=10.0,
        subscription_plan="premium",
        created_at=_now(),
        updated_at=_now(),
    )
    db.session.add(shop1)
    db.session.add(shop2)
    db.session.flush()

    # ── Subscriptions ──────────────────────────────────────────────────────
    for shop, plan in [(shop1, "standard"), (shop2, "premium")]:
        sub = Subscription(
            shop_id=shop.id,
            plan_name=plan.capitalize(),
            plan_type=plan,
            status="active",
            amount={"basic": 999, "standard": 2999, "premium": 5999}[plan],
            billing_cycle="monthly",
            start_date=_now() - timedelta(days=30),
            end_date=_now() + timedelta(days=30),
            auto_renew=True,
            payment_method="mpesa",
            created_at=_now(),
            updated_at=_now(),
        )
        db.session.add(sub)

    # ── Product Categories ─────────────────────────────────────────────────
    mboga_cats = {}
    for name, sort in [("Fruits & Vegetables", 1), ("Dairy & Eggs", 2), ("Pantry Essentials", 3)]:
        pc = ProductCategory(shop_id=shop1.id, name=name, sort_order=sort,
                             is_active=True, created_at=_now())
        db.session.add(pc)
        mboga_cats[name] = pc

    java_cats = {}
    for name, sort in [("Coffee & Tea", 1), ("Breakfast", 2), ("Main Meals", 3)]:
        pc = ProductCategory(shop_id=shop2.id, name=name, sort_order=sort,
                             is_active=True, created_at=_now())
        db.session.add(pc)
        java_cats[name] = pc

    db.session.flush()

    # ── Products — Mama Mboga ──────────────────────────────────────────────
    mboga_products = [
        # (name, desc, price, category, featured, prep_time, tags)
        ("Tomatoes (1kg)",    "Farm-fresh tomatoes from Mount Kenya region",   80,  "Fruits & Vegetables", True,  5,  ["vegetables", "fresh"]),
        ("Potatoes (1kg)",    "Premium Irish potatoes, great for chips",        60,  "Fruits & Vegetables", False, 5,  ["vegetables"]),
        ("Onions (1kg)",      "Red onions, freshly harvested",                  70,  "Fruits & Vegetables", False, 5,  ["vegetables"]),
        ("Kale / Sukuma Wiki","Fresh sukuma wiki, daily harvest",               30,  "Fruits & Vegetables", True,  5,  ["vegetables", "popular"]),
        ("Bananas (bunch)",   "Sweet ripe bananas, local variety",             100,  "Fruits & Vegetables", False, 5,  ["fruits"]),
        ("Capsicum (250g)",   "Mixed bell peppers, colorful and crunchy",       80,  "Fruits & Vegetables", False, 5,  ["vegetables"]),
        ("Fresh Milk 500ml",  "Pasteurised whole milk",                         70,  "Dairy & Eggs",        True,  2,  ["dairy", "popular"]),
        ("Eggs (tray of 30)", "Free-range farm eggs",                          420,  "Dairy & Eggs",        True,  2,  ["dairy", "eggs"]),
        ("Unga Jogoo 2kg",   "Fortified maize flour",                          200,  "Pantry Essentials",   True,  2,  ["flour", "staple"]),
        ("Sugar 1kg",         "White granulated sugar",                         130,  "Pantry Essentials",   False, 2,  ["sugar"]),
        ("Rice (1kg)",        "Premium long-grain white rice",                  150,  "Pantry Essentials",   False, 2,  ["rice", "staple"]),
        ("Cooking Oil 1L",    "Pure sunflower cooking oil",                    290,  "Pantry Essentials",   True,  2,  ["oil", "popular"]),
    ]
    for name, desc, price, cat_name, featured, prep, tags in mboga_products:
        p = Product(
            shop_id=shop1.id,
            category_id=mboga_cats[cat_name].id,
            name=name,
            description=desc,
            price=float(price),
            is_available=True,
            is_featured=featured,
            preparation_time=prep,
            tags=tags,
            total_orders=0,
            rating=4.5,
            created_at=_now(),
            updated_at=_now(),
        )
        db.session.add(p)

    # ── Products — Java House ──────────────────────────────────────────────
    java_products = [
        ("Espresso",           "Rich single-shot espresso",                    180, "Coffee & Tea",  True,  5,  ["coffee", "popular"]),
        ("Cappuccino",         "Espresso with steamed milk foam",              260, "Coffee & Tea",  True,  7,  ["coffee"]),
        ("Latte",              "Smooth espresso with warm milk",               280, "Coffee & Tea",  True,  7,  ["coffee"]),
        ("Fresh Orange Juice", "100% freshly squeezed",                        350, "Coffee & Tea",  False, 5,  ["juice", "cold"]),
        ("Breakfast Platter",  "Eggs, toast, sausages, fruit & coffee",        680, "Breakfast",     True, 15,  ["breakfast", "popular"]),
        ("Avocado Toast",      "Sourdough, smashed avo, feta & poached egg",   550, "Breakfast",     True, 10,  ["breakfast", "healthy"]),
        ("Croissant",          "Buttery flaky croissant, plain or filled",     350, "Breakfast",     False, 5,  ["pastry"]),
        ("Club Sandwich",      "Triple-decker with chicken, lettuce & tomato", 780, "Main Meals",    True, 15,  ["sandwich", "popular"]),
        ("Chicken Burger",     "Grilled chicken, brioche bun, coleslaw",       850, "Main Meals",    True, 20,  ["burger", "popular"]),
        ("Chips & Chicken",    "Crispy fries & quarter chicken, served with coleslaw", 720, "Main Meals", True, 20, ["fries", "popular"]),
    ]
    for name, desc, price, cat_name, featured, prep, tags in java_products:
        p = Product(
            shop_id=shop2.id,
            category_id=java_cats[cat_name].id,
            name=name,
            description=desc,
            price=float(price),
            is_available=True,
            is_featured=featured,
            preparation_time=prep,
            tags=tags,
            total_orders=0,
            rating=4.6,
            created_at=_now(),
            updated_at=_now(),
        )
        db.session.add(p)

    # ── Customer Addresses ─────────────────────────────────────────────────
    addresses = [
        Address(user_id=sarah.id, label="Home",  street="14 Westlands Road",
                city="Nairobi", area="Westlands", building="Westlands Apartments",
                floor="3", door="3B", latitude=-1.2680, longitude=36.8086,
                is_default=True, is_validated=True, created_at=_now(), updated_at=_now()),
        Address(user_id=sarah.id, label="Work",  street="Upper Hill Road",
                city="Nairobi", area="Upper Hill", building="Britam Tower",
                floor="12", door="1200", latitude=-1.2993, longitude=36.8124,
                is_default=False, is_validated=True, created_at=_now(), updated_at=_now()),
        Address(user_id=james.id, label="Home",  street="Ngong Road",
                city="Nairobi", area="Kilimani", building="Kilimani Heights",
                floor="2", door="2A", latitude=-1.2921, longitude=36.7898,
                is_default=True, is_validated=True, created_at=_now(), updated_at=_now()),
    ]
    for addr in addresses:
        db.session.add(addr)

    # ── Rider Locations ────────────────────────────────────────────────────
    rider_locs = [
        RiderLocation(rider_id=rider1.id, latitude=-1.2740, longitude=36.8118,
                      is_online=True, updated_at=_now()),
        RiderLocation(rider_id=rider2.id, latitude=-1.2869, longitude=36.8200,
                      is_online=True, updated_at=_now()),
    ]
    for rl in rider_locs:
        db.session.add(rl)

    # ── Welcome Notifications ──────────────────────────────────────────────
    notifs = [
        Notification(user_id=sarah.id,   title="Welcome to Tumana! 🎉",
                     message="Browse local shops and get your favourites delivered in minutes.",
                     type="system", is_read=False, created_at=_now()),
        Notification(user_id=james.id,   title="Welcome to Tumana! 🎉",
                     message="Browse local shops and get your favourites delivered in minutes.",
                     type="system", is_read=False, created_at=_now()),
        Notification(user_id=shop1_u.id, title="Shop approved ✅",
                     message="Mama Mboga Fresh Market is now live on Tumana.",
                     type="system", is_read=False, created_at=_now()),
        Notification(user_id=shop2_u.id, title="Shop approved ✅",
                     message="Java House Nairobi CBD is now live on Tumana.",
                     type="system", is_read=False, created_at=_now()),
        Notification(user_id=rider1.id,  title="Welcome, rider! 🚴",
                     message="You're verified and ready to start accepting deliveries.",
                     type="system", is_read=False, created_at=_now()),
        Notification(user_id=rider2.id,  title="Welcome, rider! 🚴",
                     message="You're verified and ready to start accepting deliveries.",
                     type="system", is_read=False, created_at=_now()),
    ]
    for n in notifs:
        db.session.add(n)

    db.session.commit()
    log.info("Seed complete — %d users, 2 shops, %d products.",
             len(all_users),
             len(mboga_products) + len(java_products))

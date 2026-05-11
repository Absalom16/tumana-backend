# Tumana Backend API

Flask + SQLAlchemy + MySQL backend for the Tumana delivery platform.

## Stack
- **Python 3.11** / Flask 3.0
- **MySQL 8** (via PyMySQL + SQLAlchemy)
- **Alembic** (via Flask-Migrate) for migrations
- **Flask-JWT-Extended** for JWT auth
- **Celery + Redis** for background tasks
- **Docker Compose** for local development

## Quick Start

### 1. Clone & configure
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 2. Run with Docker Compose
```bash
docker-compose up --build
```
The API will be available at `http://localhost:5000/api`

### 3. Create tables & seed admin
```bash
docker-compose exec api flask db upgrade
docker-compose exec api python seed.py
```

**Default admin credentials:**
- Email: `admin@tumana.co.ke`
- Password: `Admin@1234`

---

## Local Development (without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # set DATABASE_URL to your local MySQL
flask db init
flask db migrate -m "initial"
flask db upgrade
python seed.py
python wsgi.py
```

---

## API Overview

| Prefix | Description |
|---|---|
| `/api/auth` | Login, register, OTP, fingerprint, PIN |
| `/api/admin` | Admin: analytics, orders, users, payouts, subscriptions, settings |
| `/api/customer` | Customer: dashboard, orders, wallet, shops, products, addresses, checkout |
| `/api/rider` | Rider: dashboard, jobs, deliveries, earnings, location |
| `/api/shop` | Shop owner: profile, products, orders, analytics |

### Auth
All protected routes require: `Authorization: Bearer <access_token>`

### Response Format
```json
{
  "success": true,
  "message": "...",
  "data": { ... }
}
```
Errors:
```json
{
  "success": false,
  "error": "..."
}
```

---

## Roles
| Role | Description |
|---|---|
| `admin` | Platform administrator |
| `customer` | End customer placing orders |
| `rider` | Delivery rider |
| `shop_owner` | Restaurant / shop owner |

---

## Running Migrations
```bash
flask db migrate -m "description"
flask db upgrade
```

## Running Tests
```bash
pytest
```

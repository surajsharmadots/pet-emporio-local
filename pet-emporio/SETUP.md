# Pet Emporio — Dev Setup Guide

## Prerequisites

- Python 3.12
- Docker + Docker Compose
- PostgreSQL client (`psql`) — optional, for verification

---

## Step 1 — Create a Virtual Environment

> **Why?** Without a venv, `pip install` installs packages globally on your system.
> This can break other Python projects or cause version conflicts.
> Always use a venv — packages stay isolated to this project only.

Create one venv at the **repo root** (shared across all services for local dev):

```bash
cd pet-emporio/

# Create the venv
python3.12 -m venv venv

# Activate it (Linux / macOS)
source venv/bin/activate

# Activate it (Windows)
venv\Scripts\activate
```

You'll see `(venv)` at the start of your terminal prompt — that means it's active.

> **Every time you open a new terminal, re-run `source venv/bin/activate` before running any pip/python/pytest/uvicorn commands.**

To deactivate when you're done:
```bash
deactivate
```

---

## Step 2 — Install pe-common

pe-common is the shared library used by all services. Install it first.

```bash
# Make sure venv is active: (venv) should show in your prompt

cd packages/pe-common
pip install -r requirements-dev.txt
```

Verify:
```bash
python3.12 -m pytest tests/ -v
# Expected: 12 passed
```

---

## Step 3 — Environment Variables

There is **no single global `.env`** file. Each service has its own `.env.example` inside its own folder.

```
pet-emporio/
├── .env.example              ← reference only (shows all variables across all services)
├── services/
│   ├── auth-service/
│   │   └── .env.example      ← copy this to .env inside auth-service/
│   ├── user-service/
│   │   └── .env.example      ← copy this to .env inside user-service/
│   └── ...
```

For each service you want to run, go into that folder and copy its own `.env.example`:

```bash
cd services/auth-service
cp .env.example .env
# then edit .env to fill in secrets
```

> The root `.env.example` is just a full reference — you do not copy it anywhere.

---

## Step 4 — Start Infrastructure

```bash
cd infra
docker-compose up -d postgres rabbitmq redis minio mailhog jaeger
```

> **Note:** Host ports remapped to avoid conflicts with any local postgres/redis:
> - PostgreSQL → `localhost:5433` (container runs on 5432)
> - Redis → `localhost:6380` (container runs on 6379)

Wait for health checks:
```bash
docker-compose ps
# postgres, rabbitmq, redis should show: running (healthy)
```

---

## Step 5 — Verify Databases

```bash
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -c '\l'
# Should list all 10 pe_* databases:
# pe_auth, pe_users, pe_catalog, pe_orders, pe_payments,
# pe_bookings, pe_medical, pe_notifications, pe_content, pe_reports
```

---

## Step 6 — Run auth-service (dev)

```bash
# Make sure venv is active
cd services/auth-service
pip install -r requirements-dev.txt
```

Generate RSA key pair (one-time):
```bash
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
export JWT_PRIVATE_KEY="$(cat private.pem)"
export JWT_PUBLIC_KEY="$(cat public.pem)"
```

Run migrations and start:
```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8011 --reload
```

Verify:
```bash
curl http://localhost:8011/health
# → {"status":"ok","service":"auth-service"}

curl -X POST http://localhost:8011/api/v1/auth/otp/send \
  -H "Content-Type: application/json" \
  -d '{"mobile":"+919876543210"}'
# → OTP printed to logs in DEV_MODE=true
```

Run tests (no infra needed — uses in-memory DB and fake Redis):
```bash
python3.12 -m pytest tests/ -v
# Expected: 10 passed
```

---

## Step 7 — (Optional) Start Kong API Gateway

> Requires at least auth-service running first.

```bash
cd infra
docker-compose up -d kong
```

---

## Virtual Environment Quick Reference

```bash
# Create (once)
python3.12 -m venv venv

# Activate — run this every time you open a terminal
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# Check it's active
which python                    # Should point inside venv/
pip list                        # Shows only packages in this venv

# Deactivate when done
deactivate
```

---

## Service URLs

| Service          | URL                              | Credentials             |
|------------------|----------------------------------|-------------------------|
| Kong Proxy       | http://localhost:8000            | —                       |
| Kong Admin API   | http://localhost:8001            | —                       |
| RabbitMQ UI      | http://localhost:15672           | guest / guest           |
| MinIO Console    | http://localhost:9001            | minioadmin / minioadmin |
| MailHog UI       | http://localhost:8025            | —                       |
| Jaeger UI        | http://localhost:16686           | —                       |
| Keycloak         | http://localhost:8080            | admin / admin           |
| PostgreSQL       | localhost:5433                   | postgres / postgres     |
| Redis            | localhost:6380                   | —                       |

---

## Microservice Ports (direct access)

| Service              | Host Port |
|----------------------|-----------|
| auth-service         | 8011      |
| user-service         | 8012      |
| catalog-service      | 8013      |
| order-service        | 8014      |
| payment-service      | 8015      |
| booking-service      | 8016      |
| medical-service      | 8017      |
| notification-service | 8018      |
| content-service      | 8019      |
| report-service       | 8020      |

---

## Stop Everything

```bash
cd infra
docker-compose down
```

To also remove volumes (wipes all DB data):
```bash
docker-compose down -v
```

---

## Build Prompts Progress

| Prompt | Description               | Status  |
|--------|---------------------------|---------|
| 1      | pe-common library         | ✅ Done |
| 2      | Docker Compose infra      | ✅ Done |
| 3      | auth-service              | ✅ Done |
| 4      | user-service              | ⬜      |
| 5      | Kong gateway config       | ⬜      |
| 6      | catalog + content service | ⬜      |
| 7      | notification-service      | ⬜      |
| 8      | order + payment service   | ⬜      |
| 9      | booking + medical service | ⬜      |
| 10     | report + security + k8s   | ⬜      |
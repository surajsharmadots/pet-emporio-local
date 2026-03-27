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
docker-compose up -d postgres keycloak rabbitmq redis minio mailhog jaeger
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

## Step 7 — Run user-service (dev)

```bash
# Make sure venv is active
cd services/user-service
pip install -r requirements-dev.txt
```

Copy and configure env:
```bash
cp .env.example .env
# Edit .env — set JWT_PUBLIC_KEY to match auth-service's public.pem
```

Run migrations and start:
```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8012 --reload
```

Verify:
```bash
curl http://localhost:8012/health
# → {"status":"ok","service":"user-service"}
```

Run tests (no infra needed — uses in-memory DB and fake Redis):
```bash
.venv/bin/pytest tests/ -v
# Expected: 11 passed
```

---

## Step 8 — Configure Keycloak (first-time setup)

Keycloak starts automatically as part of Step 4. On **first boot**, it auto-imports the realm configuration from `keycloak/pet-emporio-realm.json` — no manual UI steps required.

This realm file sets up:
- **Realm:** `pet-emporio`
- **Roles:** `customer`, `doctor`, `seller`, `lab_technician`, `groomer`, `pharmacist`, `admin`, `sub_admin`
- **Clients:** `auth-service` (service account + token exchange), `customer-portal`, `admin-portal`, `doctor-portal`
- **Protocol mappers** on `auth-service` client: `pe_user_id`, `mobile`, `tenant_id`, `device_id`, realm roles → `roles` claim
- **Authentication flow:** OTP-first browser login
- **Token settings:** access token 15 min, SSO idle 30 min, offline session 90 days

### Enable Keycloak in auth-service

By default `KEYCLOAK_ENABLED=False` so auth-service runs without Keycloak (early local dev).
To enable it, add these to `services/auth-service/.env`:

```env
KEYCLOAK_ENABLED=true
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_REALM=pet-emporio
KEYCLOAK_CLIENT_ID=auth-service
KEYCLOAK_CLIENT_SECRET=auth-service-secret
KEYCLOAK_ADMIN_USER=admin
KEYCLOAK_ADMIN_PASSWORD=admin
```

### ⚠️ One manual step — enable token-exchange permission

The realm JSON sets `token.exchange.grant.enabled = true` on the `auth-service` client,
but Keycloak also requires a **policy** to be attached to the token-exchange permission.
This cannot be exported/imported via realm JSON — it must be done once in the UI.

1. Open **http://localhost:8080/admin** → log in (admin / admin)
2. Switch to the **pet-emporio** realm (top-left dropdown)
3. Go to **Clients → auth-service → Authorization tab → Permissions**
4. Click the **token-exchange** permission
5. Under **Policies**, click **Add policy → Client policy**
   - Name: `any-client`
   - Logic: `Positive`
   - Save
6. Back in the token-exchange permission, add `any-client` to Policies → Save

Without this step, `issue_token()` (OTP/social login token exchange) will return HTTP 403.

---

### Verify the realm loaded correctly

```bash
# Check the realm exists
curl -s http://localhost:8080/realms/pet-emporio | python3 -m json.tool | grep realm

# Log in to the Keycloak admin console
# URL:      http://localhost:8080/admin
# Username: admin
# Password: admin
# → Go to "pet-emporio" realm → Clients → verify "auth-service" client exists
```

### Re-importing after a `docker-compose down -v`

Wiping volumes removes Keycloak's database. On next `docker-compose up`, Keycloak will
auto-import the realm again from `keycloak/pet-emporio-realm.json` — no manual steps needed.

---

## Step 9 — (Optional) Start Kong API Gateway

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
| 4      | user-service              | ✅ Done |
| 5      | Kong gateway config       | ⬜      |
| 6      | catalog + content service | ⬜      |
| 7      | notification-service      | ⬜      |
| 8      | order + payment service   | ⬜      |
| 9      | booking + medical service | ⬜      |
| 10     | report + security + k8s   | ⬜      |
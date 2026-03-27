# Auth Service

Handles OTP-based authentication, JWT issuance, session management, MFA, and social login.

- **Port:** 8011 (host) → 8000 (container)
- **Database:** `pe_auth` (PostgreSQL)
- **Cache:** Redis DB 0

---

## Prerequisites

Make sure the following are running before starting this service:

```bash
cd infra
docker-compose ps
# postgres, redis, rabbitmq must show: running (healthy)
```

If not started yet:
```bash
docker-compose up -d postgres redis rabbitmq
```

---

## 1. Create & Activate Virtual Environment

> Skip this if you already activated the root-level venv (see repo SETUP.md).

```bash
# From repo root — create once
python3.12 -m venv venv

# Activate every time you open a new terminal
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows
```

You should see `(venv)` in your terminal prompt before continuing.

---

## 2. Install Dependencies

```bash
cd services/auth-service

# For local dev and running tests
pip install -r requirements-dev.txt

# For production only (no test tools)
pip install -r requirements.txt
```

---

## 3. Generate RSA Key Pair (one-time setup)

The service uses RS256 JWT — you need a private/public key pair.

```bash
cd services/auth-service

openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
```

Add the keys to your `.env` file (see Step 3).

---

## 4. Create `.env` File

> Each service has its own `.env.example` inside its own folder.
> The `.env.example` for auth-service lives at `services/auth-service/.env.example`.

Make sure you are inside the `auth-service` folder, then run:

```bash
# Must be run from inside services/auth-service/
cd pet-emporio/services/auth-service

cp .env.example .env
```

Open `.env` and fill in the keys:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/pe_auth
REDIS_URL=redis://localhost:6380/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

JWT_PRIVATE_KEY=<paste contents of private.pem — keep newlines as \n or use multiline>
JWT_PUBLIC_KEY=<paste contents of public.pem>

DEV_MODE=true
```

> **Tip:** To inline the key on one line:
> ```bash
> awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' private.pem
> ```

---

## 5. Run Database Migrations

```bash
cd services/auth-service
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 001, initial schema
```

---

## 6. Start the Service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8011 --reload
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8011
INFO:     Application startup complete.
```

---

## 7. Verify It's Working

**Health check:**
```bash
curl http://localhost:8011/health
```
```json
{"status": "ok", "service": "auth-service"}
```

**Send an OTP** (in DEV_MODE the OTP is printed to the server logs):
```bash
curl -X POST http://localhost:8011/api/v1/auth/otp/send \
  -H "Content-Type: application/json" \
  -d '{"mobile": "+919876543210"}'
```
```json
{"success": true, "data": {"message": "OTP sent successfully", "expires_in": 300}}
```

Check server logs for the OTP value, then verify it:
```bash
curl -X POST http://localhost:8011/api/v1/auth/otp/verify \
  -H "Content-Type: application/json" \
  -d '{"mobile": "+919876543210", "otp": "XXXXXX"}'
```
```json
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "uuid-...",
    "token_type": "bearer",
    "expires_in": 900
  }
}
```

**Refresh access token:**
```bash
curl -X POST http://localhost:8011/api/v1/auth/token/refresh/<session_id> \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

**Logout:**
```bash
curl -X POST http://localhost:8011/api/v1/auth/logout \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<session_id>"}'
```

**Internal token verify** (used by other services):
```bash
curl -X POST http://localhost:8011/internal/v1/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"token": "<access_token>"}'
```
```json
{"success": true, "data": {"valid": true, "user_id": "...", "roles": ["customer"]}}
```

---

## 8. Run Tests

```bash
cd services/auth-service
python3.12 -m pytest tests/ -v
```

Expected:
```
tests/test_auth.py::test_send_otp_success              PASSED
tests/test_auth.py::test_send_otp_rate_limit           PASSED
tests/test_auth.py::test_verify_otp_success            PASSED
tests/test_auth.py::test_verify_otp_wrong              PASSED
tests/test_auth.py::test_verify_otp_expired            PASSED
tests/test_auth.py::test_refresh_token_success         PASSED
tests/test_auth.py::test_refresh_token_invalid         PASSED
tests/test_auth.py::test_logout_revokes_session        PASSED
tests/test_auth.py::test_internal_verify_valid_token   PASSED
tests/test_auth.py::test_internal_verify_expired_token PASSED

10 passed
```

Tests use **fakeredis** and **SQLite in-memory** — no real DB or Redis needed.

---

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/otp/send` | None | Send OTP to mobile |
| POST | `/api/v1/auth/otp/verify` | None | Verify OTP → JWT pair |
| POST | `/api/v1/auth/token/refresh/{session_id}` | None | Refresh access token |
| POST | `/api/v1/auth/logout` | Bearer | Revoke session |
| GET | `/api/v1/auth/sessions` | Bearer | List active sessions |
| DELETE | `/api/v1/auth/sessions/{id}` | Bearer | Revoke a session |
| POST | `/api/v1/auth/mfa/setup` | Bearer | Setup TOTP MFA |
| POST | `/api/v1/auth/mfa/verify` | Bearer | Verify & enable MFA |
| POST | `/internal/v1/auth/verify` | None | Verify JWT (internal) |
| GET | `/internal/v1/auth/public-key` | None | Get RS256 public key |
| GET | `/health` | None | Health check |
| GET | `/docs` | None | Swagger UI |

---

## Rate Limits

| Rule | Limit |
|------|-------|
| OTP send per mobile | 3 requests per 10 minutes |
| OTP expiry | 5 minutes |
| Access token expiry | 15 minutes |
| Refresh token expiry | 30 days |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6380/0` | Redis connection |
| `RABBITMQ_URL` | `amqp://guest:guest@...` | RabbitMQ connection |
| `JWT_PRIVATE_KEY` | — | RS256 private key (PEM) |
| `JWT_PUBLIC_KEY` | — | RS256 public key (PEM) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token TTL |
| `OTP_EXPIRE_SECONDS` | `300` | OTP TTL (5 min) |
| `OTP_RATE_LIMIT` | `3` | Max OTPs per window |
| `OTP_RATE_WINDOW_SECONDS` | `600` | Rate limit window (10 min) |
| `DEV_MODE` | `true` | Log OTP instead of SMS |
| `MSG91_AUTH_KEY` | — | MSG91 SMS key (prod) |
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$REPO_ROOT/infra"
SERVICES_DIR="$REPO_ROOT/services"

# Colours
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

info "Starting infrastructure services..."
cd "$INFRA_DIR"
docker compose up -d postgres rabbitmq redis minio mailhog jaeger keycloak

info "Waiting for PostgreSQL to be healthy..."
MAX_WAIT=60
ELAPSED=0
until docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-postgres}" &>/dev/null; do
  if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
    error "PostgreSQL did not become healthy within ${MAX_WAIT}s. Aborting."
    exit 1
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
  echo -n "."
done
echo ""
info "PostgreSQL is healthy."

info "Waiting for RabbitMQ to be healthy..."
ELAPSED=0
until docker compose exec -T rabbitmq rabbitmq-diagnostics ping &>/dev/null; do
  if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
    warn "RabbitMQ health check timed out — continuing anyway."
    break
  fi
  sleep 3
  ELAPSED=$((ELAPSED + 3))
  echo -n "."
done
echo ""

info "Running Alembic migrations..."

SERVICES=(
  auth-service
  user-service
  catalog-service
  order-service
  payment-service
  booking-service
  medical-service
  notification-service
  content-service
  report-service
)

for svc in "${SERVICES[@]}"; do
  SVC_DIR="$SERVICES_DIR/$svc"
  if [ -f "$SVC_DIR/alembic.ini" ]; then
    info "  Migrating $svc..."
    (cd "$SVC_DIR" && alembic upgrade head) || warn "  Migration failed for $svc — skipping."
  else
    warn "  No alembic.ini found for $svc — skipping migration."
  fi
done

info "Starting microservices..."

declare -A SVC_PORTS=(
  [auth-service]=8011
  [user-service]=8012
  [catalog-service]=8013
  [order-service]=8014
  [payment-service]=8015
  [booking-service]=8016
  [medical-service]=8017
  [notification-service]=8018
  [content-service]=8019
  [report-service]=8020
)

for svc in "${SERVICES[@]}"; do
  SVC_DIR="$SERVICES_DIR/$svc"
  PORT="${SVC_PORTS[$svc]}"
  if [ -f "$SVC_DIR/main.py" ] || [ -d "$SVC_DIR/app" ]; then
    info "  Starting $svc on port $PORT..."
    (cd "$SVC_DIR" && uvicorn app.main:app --host 0.0.0.0 --port 8000 \
      --reload --log-level info \
      > "/tmp/pe-${svc}.log" 2>&1) &
    echo $! > "/tmp/pe-${svc}.pid"
  else
    warn "  $svc not yet implemented — skipping."
  fi
done

info "Starting Kong API Gateway..."
cd "$INFRA_DIR"
docker compose up -d kong

# Print all service URLs
echo ""
echo -e "${GREEN}  Pet Emporio dev environment ready${NC}"
echo ""
echo "  Infrastructure:"
echo "    PostgreSQL        →  localhost:5432"
echo "    RabbitMQ UI       →  http://localhost:15672  (guest/guest)"
echo "    Redis             →  localhost:6379"
echo "    MinIO Console     →  http://localhost:9001   (minioadmin/minioadmin)"
echo "    MailHog UI        →  http://localhost:8025"
echo "    Jaeger UI         →  http://localhost:16686"
echo "    Keycloak          →  http://localhost:8080   (admin/admin)"
echo ""
echo "  API Gateway (Kong):"
echo "    Proxy             →  http://localhost:8000"
echo "    Admin API         →  http://localhost:8001"
echo "    Admin GUI         →  https://localhost:8002"
echo ""
echo "  Microservices (direct):"
echo "    auth-service      →  http://localhost:8011"
echo "    user-service      →  http://localhost:8012"
echo "    catalog-service   →  http://localhost:8013"
echo "    order-service     →  http://localhost:8014"
echo "    payment-service   →  http://localhost:8015"
echo "    booking-service   →  http://localhost:8016"
echo "    medical-service   →  http://localhost:8017"
echo "    notification-svc  →  http://localhost:8018"
echo "    content-service   →  http://localhost:8019"
echo "    report-service    →  http://localhost:8020"
echo ""
echo "  Logs: /tmp/pe-<service>.log"
echo "  Stop: docker compose -f $INFRA_DIR/docker-compose.yml down"
echo ""
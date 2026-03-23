#!/usr/bin/env bash
# scripts/apply-kong-config.sh
# Reads the RS256 public key from auth-service, embeds it into kong.yml,
# and posts the final config to Kong's Admin API.
#
# Usage:
#   ./scripts/apply-kong-config.sh
#   KONG_ADMIN=http://localhost:8001 ./scripts/apply-kong-config.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PUBLIC_KEY_FILE="$REPO_ROOT/services/auth-service/public.pem"
KONG_YML="$REPO_ROOT/gateway/kong.yml"
KONG_ADMIN="${KONG_ADMIN:-http://localhost:8001}"
TEMP_CONFIG=$(mktemp /tmp/kong-config-XXXXX.yml)

# ── Preflight checks ──────────────────────────────────────────────────────────

if [ ! -f "$PUBLIC_KEY_FILE" ]; then
  echo "ERROR: $PUBLIC_KEY_FILE not found."
  echo "Generate RSA keys first:"
  echo "  cd services/auth-service && openssl genrsa -out private.pem 2048 && openssl rsa -in private.pem -pubout -out public.pem"
  exit 1
fi

if ! curl -sf "$KONG_ADMIN/" > /dev/null 2>&1; then
  echo "ERROR: Kong Admin API not reachable at $KONG_ADMIN"
  echo "Start Kong first: cd infra && docker-compose up -d kong"
  exit 1
fi

echo "Kong Admin API: $KONG_ADMIN  ✓"
echo "Public key:     $PUBLIC_KEY_FILE  ✓"

# ── Generate final config with embedded public key ────────────────────────────

python3 - "$REPO_ROOT" "$KONG_YML" "$TEMP_CONFIG" << 'PYEOF'
import sys

repo_root, config_file, output_file = sys.argv[1], sys.argv[2], sys.argv[3]
key_file = f"{repo_root}/services/auth-service/public.pem"

with open(key_file) as f:
    pem_lines = f.read().strip().split('\n')

# YAML block literal: "| " followed by indented PEM lines (8 spaces)
indented = '\n'.join('        ' + line for line in pem_lines)
replacement = '|\n' + indented

with open(config_file) as f:
    config = f.read()

if 'REPLACE_PUBLIC_KEY' not in config:
    print("WARNING: REPLACE_PUBLIC_KEY placeholder not found in kong.yml")
    print("         Posting config as-is (no key substitution).")
else:
    config = config.replace('REPLACE_PUBLIC_KEY', replacement)
    print("Public key embedded into config.")

with open(output_file, 'w') as f:
    f.write(config)
PYEOF

echo "Temp config:    $TEMP_CONFIG"

# ── Apply config to Kong ──────────────────────────────────────────────────────

echo "Applying config..."
RESPONSE=$(mktemp)
HTTP_STATUS=$(curl -s -o "$RESPONSE" -w "%{http_code}" \
  -X POST "$KONG_ADMIN/config" \
  -F "config=@$TEMP_CONFIG")

if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "201" ]; then
  echo ""
  echo "✓ Kong config applied successfully (HTTP $HTTP_STATUS)"
  echo ""
  echo "Routes loaded:"
  curl -s "$KONG_ADMIN/routes" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('data', []):
    print(f\"  {r['name']}: {r.get('paths', [])}\")
" 2>/dev/null || true
else
  echo ""
  echo "✗ Failed to apply Kong config (HTTP $HTTP_STATUS)"
  echo "Response:"
  cat "$RESPONSE"
  rm -f "$RESPONSE" "$TEMP_CONFIG"
  exit 1
fi

rm -f "$RESPONSE" "$TEMP_CONFIG"
echo ""
echo "Next step: run scripts/test-gateway.sh to verify routing."
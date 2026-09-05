#!/usr/bin/env bash
#
# Post-deploy smoke test: proves the deployed API can actually run a shop,
# not merely that its health endpoint returns 200.
#
#   ./deployment/scripts/smoke-test.sh                       # inside the compose network
#   API_BASE=https://api.example.com ./deployment/scripts/smoke-test.sh
#
# Creates a throwaway tenant, so it is safe to run against a live deployment
# -- but pass --cleanup to remove it afterwards.
set -euo pipefail

API_BASE="${API_BASE:-}"
SLUG="smoke-$(date +%s)"
EMAIL="$SLUG@smoke.invalid"
PASSWORD="smoke-test-passphrase-only"
CLEANUP=0
[[ "${1:-}" == "--cleanup" ]] && CLEANUP=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Without an external URL, run curl inside the api container -- the API is not
# published on the host by design.
if [[ -n "$API_BASE" ]]; then
    call() { curl -sS --max-time 20 "$@"; }
    BASE="$API_BASE/api/v1"
else
    call() { docker compose exec -T api curl -sS --max-time 20 "$@"; }
    BASE="http://localhost:8000/api/v1"
fi

json() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }
pass() { printf '  \033[32mok\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; exit 1; }

echo "Smoke test against ${API_BASE:-the compose network}"

code=$(call -o /dev/null -w '%{http_code}' "$BASE/../../health")
[[ "$code" == "200" ]] && pass "health" || fail "health returned $code"

code=$(call -o /dev/null -w '%{http_code}' -X POST "$BASE/auth/signup" \
    -H 'Content-Type: application/json' \
    -d "{\"shop_name\":\"Smoke Shop\",\"slug\":\"$SLUG\",\"owner_name\":\"Smoke Owner\",
         \"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"plan_code\":\"basic\"}")
[[ "$code" == "201" ]] && pass "signup" || fail "signup returned $code"

TOKEN=$(call -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"tenant_slug\":\"$SLUG\"}" \
    | json 'd["access_token"]')
[[ -n "$TOKEN" ]] && pass "login" || fail "login produced no token"
AUTH="Authorization: Bearer $TOKEN"

code=$(call -o /dev/null -w '%{http_code}' -X POST "$BASE/shifts/open" \
    -H "$AUTH" -H 'Content-Type: application/json' -d '{"opening_float":"0"}')
[[ "$code" == "200" ]] && pass "open shift" || fail "open shift returned $code"

# A shop with no catalog cannot sell, so create one product inline.
PRODUCT=$(call -X POST "$BASE/catalog/products" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d '{"name":"Smoke Item","sku":"SMOKE-1","price":"10.00","cost_price":"4.00","opening_stock":"5"}' \
    | json 'd["id"]')
[[ -n "$PRODUCT" ]] && pass "create product" || fail "product was not created"

ORDER=$(call -X POST "$BASE/orders" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"items\":[{\"product_id\":\"$PRODUCT\",\"quantity\":\"2\"}],
         \"payments\":[{\"method\":\"cash\",\"amount\":\"20.00\",\"tendered_amount\":\"50.00\"}]}")
NUMBER=$(echo "$ORDER" | json 'd["order_number"]')
TOTAL=$(echo "$ORDER" | json 'd["total"]')
CHANGE=$(echo "$ORDER" | json 'd["change_due"]')
[[ "$TOTAL" == "20.00" && "$CHANGE" == "30.00" ]] \
    && pass "sale $NUMBER  total $TOTAL  change $CHANGE" \
    || fail "sale arithmetic wrong: total=$TOTAL change=$CHANGE"

# Stock must have moved; a sale that does not decrement is worse than no sale.
STOCK=$(call "$BASE/catalog/products?search=SMOKE-1" -H "$AUTH" | json 'd["items"][0]["stock_quantity"]')
[[ "${STOCK%%.*}" == "3" ]] && pass "stock 5 -> $STOCK" || fail "stock is $STOCK, expected 3"

RECEIPT=$(call "$BASE/orders/$(echo "$ORDER" | json 'd["id"]')/receipt" -H "$AUTH" | json 'd["shop"]["name"]')
[[ -n "$RECEIPT" ]] && pass "receipt renders" || fail "receipt failed"

if [[ $CLEANUP -eq 1 ]]; then
    docker compose exec -T postgres psql -U "${POSTGRES_ADMIN_USER:-pos}" -d "${POSTGRES_DB:-pos}" \
        -c "DELETE FROM tenants WHERE slug = '$SLUG'" >/dev/null
    pass "cleaned up $SLUG"
else
    echo "  (left tenant '$SLUG' behind; pass --cleanup to remove it)"
fi

echo
echo "All checks passed."

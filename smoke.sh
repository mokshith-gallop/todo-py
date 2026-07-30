#!/usr/bin/env bash
# smoke.sh — end-to-end smoke tests for the "Create a Task List" story.
# Exercises POST /api/v1/lists against a live database.
#
# Usage: BASE_URL=http://127.0.0.1:8080 ./smoke.sh
# Expects DATABASE_URL (or preview-env.json) for seeding.

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
PASS=0
FAIL=0

# ── helpers ──────────────────────────────────────────────────────────────────

check() {
  local desc="$1" expected_status="$2" actual_status="$3"
  if [ "$actual_status" = "$expected_status" ]; then
    echo "  ✓ $desc (HTTP $actual_status)"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $desc — expected HTTP $expected_status, got $actual_status"
    FAIL=$((FAIL + 1))
  fi
}

assert_json() {
  # Reads JSON body from a file, runs a python assertion expression
  local desc="$1" bodyfile="$2" expr="$3"
  if python3 -c "
import sys, json
d = json.load(open('$bodyfile'))
assert $expr
" 2>/dev/null; then
    echo "  ✓ $desc"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $desc — assertion failed: $expr"
    echo "    body: $(cat "$bodyfile")"
    FAIL=$((FAIL + 1))
  fi
}

TMPDIR=$(mktemp -d)
BODY_FILE="$TMPDIR/body.json"
trap 'rm -rf "$TMPDIR"' EXIT

do_post() {
  # Usage: do_post <json_payload> [auth_header]
  local payload="$1"
  local auth="${2:-}"
  local auth_args=()
  if [ -n "$auth" ]; then
    auth_args=(-H "$auth")
  fi
  HTTP_STATUS=$(curl -s -o "$BODY_FILE" -w "%{http_code}" \
    "$BASE_URL/api/v1/lists" \
    -H "Content-Type: application/json" \
    "${auth_args[@]}" \
    -d "$payload")
}

# ── seed helper ──────────────────────────────────────────────────────────────

seed_user() {
  # Creates a user in the DB and outputs the JWT token
  # Usage: TOKEN=$(seed_user)
  local result
  result=$(cd /workspace/project && .venv/bin/python3 << 'PYEOF'
import json, uuid, os, subprocess, urllib.parse, sys

env = json.load(open("/workspace/.gallop/preview-env.json"))["backend"]
db_url = env["DATABASE_URL"]
parsed = urllib.parse.urlparse(db_url)
qs = urllib.parse.parse_qs(parsed.query)

sys.path.insert(0, "/workspace/project")
from jose import jwt as jose_jwt

user_id = str(uuid.uuid4())
email = f"smoke-{uuid.uuid4().hex[:8]}@test.com"
token = jose_jwt.encode(
    {"sub": user_id, "email": email},
    "dev-secret-key-change-in-production",
    algorithm="HS256",
)

env_vars = os.environ.copy()
env_vars["PGPASSWORD"] = parsed.password or ""
env_vars["PGSSLMODE"] = (qs.get("sslmode") or ["prefer"])[0]

sql = f"INSERT INTO \"user\" (id, email, password_hash, created_at, updated_at) VALUES ('{user_id}', '{email}', 'hashed', NOW(), NOW());"
r = subprocess.run(
    ["psql", "-h", parsed.hostname, "-p", str(parsed.port or 5432),
     "-U", parsed.username, "-d", parsed.path.lstrip("/"), "-c", sql],
    env=env_vars, capture_output=True, text=True
)
if r.returncode != 0:
    print(f"psql error: {r.stderr}", file=sys.stderr)
    sys.exit(1)

# Output as user_id<TAB>token
print(f"{user_id}\t{token}")
PYEOF
  )
  echo "$result"
}

# ── Seed main user ───────────────────────────────────────────────────────────

echo "▶ Seeding test user …"
SEED_RESULT=$(seed_user)
USER_ID=$(echo "$SEED_RESULT" | cut -f1)
TOKEN=$(echo "$SEED_RESULT" | cut -f2)
AUTH="Authorization: Bearer $TOKEN"
echo "  user_id=$USER_ID"
echo ""

# ── AC1: valid name → 201 with id, name, position, timestamps in camelCase ───

echo "▶ AC1: Create list with valid name"
do_post '{"name": "Groceries"}' "$AUTH"
check "POST /api/v1/lists → 201" 201 "$HTTP_STATUS"
assert_json "response has 'id'" "$BODY_FILE" "'id' in d"
assert_json "response has 'name'" "$BODY_FILE" "'name' in d"
assert_json "response has 'position'" "$BODY_FILE" "'position' in d"
assert_json "response has 'createdAt' (camelCase)" "$BODY_FILE" "'createdAt' in d"
assert_json "response has 'updatedAt' (camelCase)" "$BODY_FILE" "'updatedAt' in d"
assert_json "response has 'deletedAt' (camelCase)" "$BODY_FILE" "'deletedAt' in d"
assert_json "no snake_case keys" "$BODY_FILE" "'created_at' not in d and 'updated_at' not in d"
assert_json "name is 'Groceries'" "$BODY_FILE" "d['name'] == 'Groceries'"
assert_json "deletedAt is null" "$BODY_FILE" "d['deletedAt'] is None"
echo ""

# ── AC1: exactly 120 chars accepted ──────────────────────────────────────────

echo "▶ AC1: Name exactly 120 characters accepted"
NAME120=$(python3 -c "print('a' * 120)")
do_post "{\"name\": \"$NAME120\"}" "$AUTH"
check "120-char name → 201" 201 "$HTTP_STATUS"
echo ""

# ── AC2: blank name → 422 ───────────────────────────────────────────────────

echo "▶ AC2: Blank name rejected"
do_post '{"name": "   "}' "$AUTH"
check "blank name → 422" 422 "$HTTP_STATUS"
assert_json "error code is validation_error" "$BODY_FILE" "d['error']['code'] == 'validation_error'"
echo ""

# ── AC2: empty name → 422 ───────────────────────────────────────────────────

echo "▶ AC2: Empty name rejected"
do_post '{"name": ""}' "$AUTH"
check "empty name → 422" 422 "$HTTP_STATUS"
assert_json "error code is validation_error" "$BODY_FILE" "d['error']['code'] == 'validation_error'"
echo ""

# ── AC3: name > 120 chars → 422 ─────────────────────────────────────────────

echo "▶ AC3: Name exceeding 120 characters rejected"
NAME121=$(python3 -c "print('x' * 121)")
do_post "{\"name\": \"$NAME121\"}" "$AUTH"
check "121-char name → 422" 422 "$HTTP_STATUS"
assert_json "error code is validation_error" "$BODY_FILE" "d['error']['code'] == 'validation_error'"
assert_json "error details mention 'name'" "$BODY_FILE" "any(det['field'] == 'name' for det in d['error']['details'])"
echo ""

# ── AC4: list is owner-scoped ────────────────────────────────────────────────

echo "▶ AC4: List is owner-scoped to creating user"
do_post '{"name": "Private List"}' "$AUTH"
check "create private list → 201" 201 "$HTTP_STATUS"

LIST_ID=$(python3 -c "import json; print(json.load(open('$BODY_FILE'))['id'])")

# Verify in DB that user_id matches
DB_USER_ID=$(cd /workspace/project && .venv/bin/python3 << PYEOF
import json, os, subprocess, urllib.parse

env = json.load(open("/workspace/.gallop/preview-env.json"))["backend"]
db_url = env["DATABASE_URL"]
parsed = urllib.parse.urlparse(db_url)
qs = urllib.parse.parse_qs(parsed.query)

env_vars = os.environ.copy()
env_vars["PGPASSWORD"] = parsed.password or ""
env_vars["PGSSLMODE"] = (qs.get("sslmode") or ["prefer"])[0]

sql = "SELECT user_id FROM task_list WHERE id = '$LIST_ID';"
result = subprocess.run(
    ["psql", "-h", parsed.hostname, "-p", str(parsed.port or 5432),
     "-U", parsed.username, "-d", parsed.path.lstrip("/"),
     "-t", "-A", "-c", sql],
    env=env_vars, capture_output=True, text=True
)
print(result.stdout.strip())
PYEOF
)

if [ "$DB_USER_ID" = "$USER_ID" ]; then
  echo "  ✓ list user_id matches creating user"
  PASS=$((PASS + 1))
else
  echo "  ✗ list user_id mismatch: expected $USER_ID, got $DB_USER_ID"
  FAIL=$((FAIL + 1))
fi
echo ""

# ── AC5: explicit position honored ──────────────────────────────────────────

echo "▶ AC5: Explicit position honored"
do_post '{"name": "Explicit Pos", "position": 5000.0}' "$AUTH"
check "explicit position → 201" 201 "$HTTP_STATUS"
assert_json "position is 5000.0" "$BODY_FILE" "d['position'] == 5000.0"
echo ""

# ── AC5: position 0.0 accepted ──────────────────────────────────────────────

echo "▶ AC5: Position 0.0 is accepted"
do_post '{"name": "Zero Pos", "position": 0.0}' "$AUTH"
check "position 0.0 → 201" 201 "$HTTP_STATUS"
assert_json "position is 0.0" "$BODY_FILE" "d['position'] == 0.0"
echo ""

# ── AC5: auto-assigned position (fresh user) ────────────────────────────────

echo "▶ AC5: Auto-assigned position for fresh user"

SEED2=$(seed_user)
FRESH_TOKEN=$(echo "$SEED2" | cut -f2)
FRESH_AUTH="Authorization: Bearer $FRESH_TOKEN"

# First list — should get position 1000
do_post '{"name": "First List"}' "$FRESH_AUTH"
check "first auto-positioned list → 201" 201 "$HTTP_STATUS"
assert_json "first list position is 1000.0" "$BODY_FILE" "d['position'] == 1000.0"

# Second list — should get position 2000
do_post '{"name": "Second List"}' "$FRESH_AUTH"
check "second auto-positioned list → 201" 201 "$HTTP_STATUS"
assert_json "second list position is 2000.0" "$BODY_FILE" "d['position'] == 2000.0"
echo ""

# ── Auth: no token → 401 ────────────────────────────────────────────────────

echo "▶ Auth: Missing auth token → 401"
do_post '{"name": "No Auth"}'
check "no auth → 401" 401 "$HTTP_STATUS"
echo ""

# ── Summary ──────────────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════"
echo "  Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi

echo "All smoke tests passed!"
exit 0

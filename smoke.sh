#!/usr/bin/env bash
# smoke.sh — end-to-end smoke tests for the Task List stories.
# Exercises POST /api/v1/lists and PATCH /api/v1/lists/{id} against a live database.
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

do_patch() {
  # Usage: do_patch <list_id> <json_payload> [auth_header]
  local list_id="$1"
  local payload="$2"
  local auth="${3:-}"
  local auth_args=()
  if [ -n "$auth" ]; then
    auth_args=(-H "$auth")
  fi
  HTTP_STATUS=$(curl -s -o "$BODY_FILE" -w "%{http_code}" \
    -X PATCH \
    "$BASE_URL/api/v1/lists/$list_id" \
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

echo "▶ Auth: Missing auth token → 401 (POST)"
do_post '{"name": "No Auth"}'
check "no auth POST → 401" 401 "$HTTP_STATUS"
echo ""

# ═════════════════════════════════════════════════════════════════════════════
#  UPDATE LIST — PATCH /api/v1/lists/{list_id}
# ═════════════════════════════════════════════════════════════════════════════

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Update a Task List (PATCH)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Seed a dedicated user + list for PATCH tests
echo "▶ Seeding PATCH test user …"
PATCH_SEED=$(seed_user)
PATCH_USER_ID=$(echo "$PATCH_SEED" | cut -f1)
PATCH_TOKEN=$(echo "$PATCH_SEED" | cut -f2)
PATCH_AUTH="Authorization: Bearer $PATCH_TOKEN"

# Create a list to update
do_post '{"name": "Original Name", "position": 1000.0}' "$PATCH_AUTH"
PATCH_LIST_ID=$(python3 -c "import json; print(json.load(open('$BODY_FILE'))['id'])")
ORIGINAL_UPDATED_AT=$(python3 -c "import json; print(json.load(open('$BODY_FILE'))['updatedAt'])")
echo "  list_id=$PATCH_LIST_ID"
echo ""

# ── Update AC1: PATCH with new name → 200 ───────────────────────────────────

echo "▶ Update AC1: Rename list"
sleep 0.1  # ensure updatedAt differs
do_patch "$PATCH_LIST_ID" '{"name": "Renamed List"}' "$PATCH_AUTH"
check "PATCH name → 200" 200 "$HTTP_STATUS"
assert_json "name is 'Renamed List'" "$BODY_FILE" "d['name'] == 'Renamed List'"
assert_json "id unchanged" "$BODY_FILE" "d['id'] == '$PATCH_LIST_ID'"
assert_json "position unchanged (1000)" "$BODY_FILE" "d['position'] == 1000.0"
assert_json "updatedAt changed" "$BODY_FILE" "d['updatedAt'] != '$ORIGINAL_UPDATED_AT'"
assert_json "response uses camelCase" "$BODY_FILE" "'createdAt' in d and 'updatedAt' in d and 'created_at' not in d"
echo ""

# ── Update AC2: PATCH with new position → 200 ───────────────────────────────

echo "▶ Update AC2: Update position"
do_patch "$PATCH_LIST_ID" '{"position": 2500.0}' "$PATCH_AUTH"
check "PATCH position → 200" 200 "$HTTP_STATUS"
assert_json "position is 2500.0" "$BODY_FILE" "d['position'] == 2500.0"
assert_json "name preserved" "$BODY_FILE" "d['name'] == 'Renamed List'"
echo ""

# ── Update AC3: blank name → 422 ────────────────────────────────────────────

echo "▶ Update AC3: Blank name rejected"
do_patch "$PATCH_LIST_ID" '{"name": "   "}' "$PATCH_AUTH"
check "blank name → 422" 422 "$HTTP_STATUS"
assert_json "error code is validation_error" "$BODY_FILE" "d['error']['code'] == 'validation_error'"
echo ""

# ── Update AC3: name > 120 chars → 422 ──────────────────────────────────────

echo "▶ Update AC3: Name > 120 chars rejected"
NAME121=$(python3 -c "print('x' * 121)")
do_patch "$PATCH_LIST_ID" "{\"name\": \"$NAME121\"}" "$PATCH_AUTH"
check "121-char name → 422" 422 "$HTTP_STATUS"
assert_json "error code is validation_error" "$BODY_FILE" "d['error']['code'] == 'validation_error'"
assert_json "error details mention name" "$BODY_FILE" "any(det['field'] == 'name' for det in d['error']['details'])"
echo ""

# ── Update AC3: empty body → 422 ────────────────────────────────────────────

echo "▶ Update AC3: Empty body rejected"
do_patch "$PATCH_LIST_ID" '{}' "$PATCH_AUTH"
check "empty body → 422" 422 "$HTTP_STATUS"
assert_json "error code is validation_error" "$BODY_FILE" "d['error']['code'] == 'validation_error'"
echo ""

# ── Update AC4: other user's list → 404 ─────────────────────────────────────

echo "▶ Update AC4: Other user's list → 404"
SEED_OTHER=$(seed_user)
OTHER_TOKEN=$(echo "$SEED_OTHER" | cut -f2)
OTHER_AUTH="Authorization: Bearer $OTHER_TOKEN"

do_patch "$PATCH_LIST_ID" '{"name": "Hijacked"}' "$OTHER_AUTH"
check "other user's list → 404" 404 "$HTTP_STATUS"
assert_json "error code is resource_not_found" "$BODY_FILE" "d['error']['code'] == 'resource_not_found'"
echo ""

# ── Update AC4: non-existent list → 404 ─────────────────────────────────────

echo "▶ Update AC4: Non-existent list → 404"
FAKE_UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
do_patch "$FAKE_UUID" '{"name": "Ghost"}' "$PATCH_AUTH"
check "non-existent list → 404" 404 "$HTTP_STATUS"
assert_json "error code is resource_not_found" "$BODY_FILE" "d['error']['code'] == 'resource_not_found'"
echo ""

# ── Update AC5: position rebalancing ────────────────────────────────────────

echo "▶ Update AC5: Position rebalancing when gap < 1e-6"

# Seed a fresh user with 3 lists for rebalancing
SEED_REBAL=$(seed_user)
REBAL_USER_ID=$(echo "$SEED_REBAL" | cut -f1)
REBAL_TOKEN=$(echo "$SEED_REBAL" | cut -f2)
REBAL_AUTH="Authorization: Bearer $REBAL_TOKEN"

do_post '{"name": "List A", "position": 1000.0}' "$REBAL_AUTH"
LIST_A_ID=$(python3 -c "import json; print(json.load(open('$BODY_FILE'))['id'])")
do_post '{"name": "List B", "position": 2000.0}' "$REBAL_AUTH"
LIST_B_ID=$(python3 -c "import json; print(json.load(open('$BODY_FILE'))['id'])")
do_post '{"name": "List C", "position": 3000.0}' "$REBAL_AUTH"
LIST_C_ID=$(python3 -c "import json; print(json.load(open('$BODY_FILE'))['id'])")

# Move List C to within 1e-6 of List A → triggers rebalance
do_patch "$LIST_C_ID" '{"position": 1000.0000001}' "$REBAL_AUTH"
check "PATCH position (trigger rebalance) → 200" 200 "$HTTP_STATUS"

# Verify rebalanced positions via DB
REBAL_POSITIONS=$(cd /workspace/project && .venv/bin/python3 << PYEOF
import json, os, subprocess, urllib.parse

env = json.load(open("/workspace/.gallop/preview-env.json"))["backend"]
db_url = env["DATABASE_URL"]
parsed = urllib.parse.urlparse(db_url)
qs = urllib.parse.parse_qs(parsed.query)

env_vars = os.environ.copy()
env_vars["PGPASSWORD"] = parsed.password or ""
env_vars["PGSSLMODE"] = (qs.get("sslmode") or ["prefer"])[0]

sql = "SELECT position FROM task_list WHERE user_id = '$REBAL_USER_ID' AND deleted_at IS NULL ORDER BY position;"
result = subprocess.run(
    ["psql", "-h", parsed.hostname, "-p", str(parsed.port or 5432),
     "-U", parsed.username, "-d", parsed.path.lstrip("/"),
     "-t", "-A", "-c", sql],
    env=env_vars, capture_output=True, text=True
)
positions = [float(p) for p in result.stdout.strip().split('\n') if p]
print(','.join(str(int(p)) for p in positions))
PYEOF
)

if [ "$REBAL_POSITIONS" = "1000,2000,3000" ]; then
  echo "  ✓ positions rebalanced to 1000, 2000, 3000"
  PASS=$((PASS + 1))
else
  echo "  ✗ expected positions 1000,2000,3000, got $REBAL_POSITIONS"
  FAIL=$((FAIL + 1))
fi
echo ""

# ── Update AC6: both name and position updated atomically ───────────────────

echo "▶ Update AC6: Atomic update of name and position"
do_patch "$PATCH_LIST_ID" '{"name": "Both Updated", "position": 7777.0}' "$PATCH_AUTH"
check "PATCH both fields → 200" 200 "$HTTP_STATUS"
assert_json "name is 'Both Updated'" "$BODY_FILE" "d['name'] == 'Both Updated'"
assert_json "position is 7777.0" "$BODY_FILE" "d['position'] == 7777.0"
echo ""

# ── Update Auth: missing token → 401 ────────────────────────────────────────

echo "▶ Update Auth: Missing auth token → 401 (PATCH)"
do_patch "$PATCH_LIST_ID" '{"name": "No Auth"}'
check "no auth PATCH → 401" 401 "$HTTP_STATUS"
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

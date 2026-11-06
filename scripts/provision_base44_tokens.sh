#!/usr/bin/env bash
# Provision the demo API tokens a Base44 Superagent needs for Phase 3.
#
# Run this on the environment that owns the database you will demo against —
# typically a Render shell (`render shell` then this script), or locally.
# Creates ONE officer token and ONE supervisor token (the "second human" Phase 3
# acceptance requires) and prints each raw token exactly once; paste them into
# Base44 encrypted secrets.
#
# Usage:
#   ./scripts/provision_base44_tokens.sh <officer-username> <supervisor-username> [days]
#
# Required env: the same DJANGO_SETTINGS_MODULE / USE_POSTGRES the deployed
# service uses. On Render, `python manage.py` already runs with the right env.

set -euo pipefail

OFFICER_USER="${1:?usage: $0 <officer-username> <supervisor-username> [days]}"
SUPERVISOR_USER="${2:?usage: $0 <officer-username> <supervisor-username> [days]}"
DAYS="${3:-90}"

PYTHON="${PYTHON:-python}"

echo "Provisioning Base44 demo tokens (valid ${DAYS} days)..."
echo "Paste each raw token into Base44 encrypted secrets (KACHIENG_API_TOKEN / KACHIENG_API_TOKEN_SUPERVISOR)."
echo

echo "=== Officer token (request advisories + read) ==="
"${PYTHON}" manage.py generate_api_token \
    --user "${OFFICER_USER}" \
    --name "base44-demo-officer" \
    --scopes advisories:request advisories:read token:introspect \
    --days "${DAYS}"

echo
echo "=== Supervisor token (second human: read + approve) ==="
"${PYTHON}" manage.py generate_api_token \
    --user "${SUPERVISOR_USER}" \
    --name "base44-demo-supervisor" \
    --scopes advisories:request advisories:read approvals:record token:introspect \
    --days "${DAYS}"

echo
echo "Done. The raw tokens above are shown ONCE; only their SHA-256 hash is stored."
echo "Revoke later with: POST /api/v1/token/revoke/ (Bearer <the token>)."

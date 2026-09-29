#!/usr/bin/env bash
set -euo pipefail
printf '{"%s":"%s"}\n' "${AIRFLOW_ADMIN_USERNAME:-admin}" "${AIRFLOW_ADMIN_PASSWORD:-sod-local-2026}" > /opt/airflow/simple_auth_manager_passwords.json
exec /entrypoint "$@"

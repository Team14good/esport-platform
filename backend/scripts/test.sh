#!/usr/bin/env bash
# 用法：bash scripts/test.sh [pytest 參數]，例如 bash scripts/test.sh -k audit

set -e
set -x

FASTAPI_ENV=development coverage run -m pytest tests/ "$@"
coverage report
coverage html --title "coverage"

#! /usr/bin/env bash

set -e
set -x

# 執行資料庫遷移
alembic upgrade head

# 建立初始資料（第一個平台管理員與示範資料）
python -m app.initial_data

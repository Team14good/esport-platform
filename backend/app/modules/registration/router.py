"""registration 的 HTTP 端點：帳號層級權限、開啟並提交交易（router 才能 commit）。"""

from fastapi import APIRouter

router = APIRouter(tags=["registration"])

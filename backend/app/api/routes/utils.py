from fastapi import APIRouter

router = APIRouter(prefix="/utils", tags=["utils"])


# 路徑不帶結尾斜線；帶斜線時 FastAPI 會回 307 轉址。
@router.get("/health-check")
async def health_check() -> bool:
    return True

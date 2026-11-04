from fastapi import APIRouter

from app.api.routes import utils
from app.modules.competition.router import router as competition_router
from app.modules.disputes.router import router as disputes_router
from app.modules.identity import service as identity_service
from app.modules.identity.router import router as identity_router
from app.modules.notifications.router import router as notifications_router
from app.modules.registration.router import router as registration_router
from app.modules.tournaments import service as tournaments_service
from app.modules.tournaments.router import router as tournaments_router

# identity 是最底層、不能呼叫 tournaments；「裁判」身分由組裝層接上（Story 4.4 S13）
identity_service.register_referee_lookup(
    lambda session, account_id: tournaments_service.has_referee_role(
        session, account_id=account_id
    )
)

api_router = APIRouter()
api_router.include_router(utils.router)
api_router.include_router(identity_router)
api_router.include_router(tournaments_router)
api_router.include_router(registration_router)
api_router.include_router(competition_router)
api_router.include_router(disputes_router)
api_router.include_router(notifications_router)

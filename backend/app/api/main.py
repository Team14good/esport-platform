from fastapi import APIRouter

from app.api.routes import utils
from app.modules.competition.router import router as competition_router
from app.modules.disputes.router import router as disputes_router
from app.modules.identity.router import router as identity_router
from app.modules.notifications.router import router as notifications_router
from app.modules.registration.router import router as registration_router
from app.modules.tournaments.router import router as tournaments_router

api_router = APIRouter()
api_router.include_router(utils.router)
api_router.include_router(identity_router)
api_router.include_router(tournaments_router)
api_router.include_router(registration_router)
api_router.include_router(competition_router)
api_router.include_router(disputes_router)
api_router.include_router(notifications_router)

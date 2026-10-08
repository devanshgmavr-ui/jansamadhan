from fastapi import APIRouter

from app.api.v1.routers import auth, collaborations, contributions, government, problems, solutions

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(problems.router)
api_router.include_router(problems.users_router)
api_router.include_router(solutions.router)
api_router.include_router(solutions.problems_router)
api_router.include_router(solutions.users_router)
api_router.include_router(contributions.router)
api_router.include_router(contributions.users_router)
api_router.include_router(collaborations.router)
api_router.include_router(collaborations.users_router)
api_router.include_router(government.router)

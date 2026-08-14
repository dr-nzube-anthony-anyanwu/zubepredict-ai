from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from zubepredict_core.shared.config import get_settings

from zubepredict_api.routes.account_links import router as account_links_router
from zubepredict_api.routes.analysis import router as analysis_router
from zubepredict_api.routes.dashboard import router as dashboard_router
from zubepredict_api.routes.datasets import router as datasets_router
from zubepredict_api.routes.decisions import router as decisions_router
from zubepredict_api.routes.experiments import router as experiments_router
from zubepredict_api.routes.health import router as health_router
from zubepredict_api.routes.hermes import router as hermes_router

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(account_links_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(datasets_router, prefix="/api/v1")
app.include_router(decisions_router, prefix="/api/v1")
app.include_router(experiments_router, prefix="/api/v1")
app.include_router(hermes_router, prefix="/api/v1")

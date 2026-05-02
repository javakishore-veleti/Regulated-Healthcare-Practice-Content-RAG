from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from common.dtos import GetAppConfigReqDTO, GetAppConfigRespDTO
from common.return_codes import RC_OK
from common.tracing import traced
from service.config_service import IConfigService

router = APIRouter(prefix="/config", tags=["config"])


def get_config_service(request: Request) -> IConfigService:
    return request.app.state.config_service


@router.get(
    "",
    response_model=GetAppConfigRespDTO,
    summary="Runtime config for the admin portal",
    description=(
        "The admin SPA fetches this at bootstrap to learn deployment-specific values "
        "(Airflow UI URL, future feature toggles). Allows the same image to run in "
        "any environment without rebuild — values come from FastAPI settings (env / "
        "cloud secret manager). Payload lives under `respCtxData`."
    ),
)
@traced("config.api.get_app_config")
async def get_app_config_handler(
    svc: Annotated[IConfigService, Depends(get_config_service)],
) -> GetAppConfigRespDTO:
    req = GetAppConfigReqDTO()
    resp = GetAppConfigRespDTO()
    rc = await svc.get_app_config(req, resp)
    if rc != RC_OK:
        raise HTTPException(status_code=500, detail="failed to read app config")
    return resp

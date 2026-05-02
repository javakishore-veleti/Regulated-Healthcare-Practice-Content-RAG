from typing import Protocol

from common.dtos import GetAppConfigReqDTO, GetAppConfigRespDTO
from common.return_codes import RC_OK
from common.settings import Settings
from common.tracing import traced


class IConfigService(Protocol):
    async def get_app_config(
        self, req: GetAppConfigReqDTO, resp: GetAppConfigRespDTO
    ) -> int: ...


class ConfigService:
    """Surfaces deployment-specific runtime config to the admin portal.

    The admin portal is a static SPA — the same artifact runs in every environment.
    Anything that varies per deployment (Airflow ingress URL, future feature toggles,
    etc.) is read from `Settings` (env / cloud secret manager) and returned here so
    the SPA can adapt at runtime without rebuilding.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @traced("config.get_app_config")
    async def get_app_config(
        self, req: GetAppConfigReqDTO, resp: GetAppConfigRespDTO
    ) -> int:
        resp.respCtxData["airflowUiBase"] = self._settings.effective_airflow_ui_base
        return RC_OK

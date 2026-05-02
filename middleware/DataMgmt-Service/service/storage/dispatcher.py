from common.dtos import IngestDataSetRespDTO
from common.return_codes import RC_VALIDATION_ERROR
from service.storage.storage_handler import IStorageHandler


class StorageDispatcher:
    """Looks up a handler by `endpoints.location_type`. New destination types are added
    by registering a new handler — no edits inside DAGs or services."""

    def __init__(self) -> None:
        self._handlers: dict[str, IStorageHandler] = {}

    def register(self, location_type: str, handler: IStorageHandler) -> None:
        self._handlers[location_type] = handler

    def resolve(self, location_type: str, resp: IngestDataSetRespDTO) -> IStorageHandler | None:
        handler = self._handlers.get(location_type)
        if handler is None:
            resp.respCtxData["error_text"] = (
                f"no storage handler registered for location_type={location_type!r}"
            )
            return None
        return handler

    @property
    def supported_location_types(self) -> list[str]:
        return sorted(self._handlers.keys())

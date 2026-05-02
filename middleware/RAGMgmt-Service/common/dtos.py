from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _BaseDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

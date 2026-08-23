from typing import Literal

from pydantic import BaseModel


class LocalShutdownResponse(BaseModel):
    status: Literal["accepted"]
    message: str

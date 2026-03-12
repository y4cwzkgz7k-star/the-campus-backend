import uuid
from pydantic import BaseModel


class SportOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    icon: str | None

    model_config = {"from_attributes": True}

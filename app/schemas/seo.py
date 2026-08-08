from pydantic import BaseModel, ConfigDict


class SeoMetaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    path: str
    title: str | None
    meta_description: str | None
    og_image_url: str | None
    canonical_url: str | None


class SeoMetaUpsert(BaseModel):
    path: str
    title: str | None = None
    meta_description: str | None = None
    og_image_url: str | None = None
    canonical_url: str | None = None

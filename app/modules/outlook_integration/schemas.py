from pydantic import BaseModel


class OutlookConnectionOut(BaseModel):
    id: str
    outlook_address: str
    is_active: bool
    connected_at: str | None = None


class OutlookConnectUrlOut(BaseModel):
    authorization_url: str


class SyncResult(BaseModel):
    checked: int
    inserted: int
    skipped_existing: int

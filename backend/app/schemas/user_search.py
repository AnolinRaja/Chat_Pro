from pydantic import BaseModel


class UserSearchResult(BaseModel):
    id: str
    name: str
    email: str


class UserSearchResponse(BaseModel):
    users: list[UserSearchResult]
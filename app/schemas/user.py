from pydantic import BaseModel, EmailStr, Field
from typing import Literal

class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(..., alias='name')  # name in the API
    password: str
    role: Literal["FACULTY", "STUDENT"]

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    username: str = Field(..., alias='name')  # name in the API
    email: EmailStr
    role: Literal["FACULTY", "STUDENT"]

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

from pydantic import BaseModel, EmailStr

class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    email: EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

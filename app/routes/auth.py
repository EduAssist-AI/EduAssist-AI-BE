# app/routes/auth.py
from fastapi import APIRouter, HTTPException, Depends
from app.schemas.user import UserRegister, UserLogin
from app.db.mongo import db
from app.utils.auth import get_current_user, hash_password, verify_password, create_access_token
from bson import ObjectId

router = APIRouter()

@router.post("/register")
async def register_user(user: UserRegister):
    existing_user = await db["users"].find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered.")
    
    hashed_pw = hash_password(user.password)
    user_doc = {
        "email": user.email,
        "username": user.username,
        "password": hashed_pw
    }
    result = await db["users"].insert_one(user_doc)
    return {"message": "User registered", "user_id": str(result.inserted_id)}

@router.post("/login")
async def login(user: UserLogin):
    user_doc = await db["users"].find_one({"email": user.email})
    if not user_doc or not verify_password(user.password, user_doc["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    
    token = create_access_token({"sub": str(user_doc["_id"]), "username": user_doc["username"]})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/protected-route")
async def protected_route(current_user=Depends(get_current_user)):
    return {"message": f"Hello, {current_user['username']}!"}
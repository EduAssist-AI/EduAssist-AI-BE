# app/routes/auth.py
from fastapi import APIRouter, HTTPException, Depends, status
from app.schemas.user import UserRegister, UserLogin, UserOut, Token
from app.db.mongo import db
from app.utils.auth import get_current_user, hash_password, verify_password, create_access_token
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_user(user: UserRegister):
    existing_user = await db["users"].find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered.")
    
    hashed_pw = hash_password(user.password)
    user_doc = {
        "email": user.email,
        "username": user.username,  # name field from API
        "password": hashed_pw,
        "role": user.role,
        "created_at": datetime.utcnow(),
        "last_login": None
    }
    result = await db["users"].insert_one(user_doc)
    return {
        "userId": str(result.inserted_id),
        "email": user.email,
        "role": user.role,
        "token": create_access_token({"sub": str(result.inserted_id), "username": user.username, "role": user.role})
    }

@router.post("/login", response_model=Token)
async def login(user: UserLogin):
    user_doc = await db["users"].find_one({"email": user.email})
    if not user_doc or not verify_password(user.password, user_doc["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    
    # Update last login
    await db["users"].update_one(
        {"_id": user_doc["_id"]},
        {"$set": {"last_login": datetime.utcnow()}}
    )
    
    token_data = {
        "sub": str(user_doc["_id"]), 
        "username": user_doc["username"],
        "role": user_doc["role"]
    }
    token = create_access_token(token_data)
    return {
        "access_token": token,
        "token_type": "bearer"
    }

@router.get("/protected-route", response_model=dict)
async def protected_route(current_user=Depends(get_current_user)):
    return {"message": f"Hello, {current_user['username']}!", "role": current_user.get('role', 'unknown')}
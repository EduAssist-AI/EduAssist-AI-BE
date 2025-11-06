import pytest
import warnings
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.user import UserRegister, UserLogin
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from app.utils.auth import hash_password, create_access_token, verify_password
from datetime import timedelta

# Suppress deprecation and other warnings for this test file
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*datetime.datetime.utcnow.*")

# Test user credentials
test_email = "prit@gmail.com"
test_password = "12345"
test_username = "prit"
test_role = "FACULTY"

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as tc:
        yield tc

@pytest.fixture
def mock_db():
    with patch('app.routes.auth.db') as mock_auth_db, \
         patch('app.utils.auth.db') as mock_utils_db:
        # Mock for bracket notation access (db["users"]...)
        mock_auth_db["users"].find_one = AsyncMock(return_value=None)
        mock_auth_db["users"].insert_one = AsyncMock(return_value=type('obj', (object,), {'inserted_id' : 'some_id'}))
        mock_auth_db["users"].update_one = AsyncMock(return_value=type('obj', (object,), {'modified_count': 1}))
        mock_utils_db["users"].find_one = AsyncMock(return_value=None)
        
        # Mock for dot notation access (db.users...)
        type(mock_auth_db).users = mock_auth_db["users"]
        type(mock_utils_db).users = mock_utils_db["users"]
        
        yield {"auth_db": mock_auth_db, "utils_db": mock_utils_db}

@pytest.mark.asyncio
async def test_login_user(client: TestClient, mock_db):
    hashed_pw = hash_password(test_password)
    user_doc = {"_id": ObjectId("652a1a9a0a8e7c1b7c8e7c1b"), "email": test_email, "username": test_username, "password": hashed_pw, "role": test_role}
    mock_db["auth_db"]["users"].find_one.return_value = user_doc
    
    with patch('app.routes.auth.verify_password', return_value=True), \
         patch('app.routes.auth.create_access_token', return_value="mock_access_token"):
        user_data = {"email": test_email, "password": test_password}
        response = client.post("/auth/login", json=user_data)
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"

    # Test invalid credentials
    mock_db["auth_db"]["users"].find_one.return_value = None # User not found
    response = client.post("/auth/login", json=user_data)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials."

    mock_db["auth_db"]["users"].find_one.return_value = user_doc
    with patch('app.routes.auth.verify_password', return_value=False): # Incorrect password
        response = client.post("/auth/login", json=user_data)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials."

@pytest.mark.asyncio
async def test_protected_route(client: TestClient, mock_db):
    hashed_pw = hash_password(test_password)
    user_doc = {"_id": ObjectId("652a1a9a0a8e7c1b7c8e7c1b"), "email": test_email, "username": test_username, "password": hashed_pw, "role": test_role}
    
    # Mock for login step - find user by email
    mock_db["auth_db"]["users"].find_one.return_value = user_doc
    
    # Create a proper token with the user info encoded
    proper_token = create_access_token({"sub": str(user_doc["_id"]), "username": test_username, "role": test_role})
    
    with patch('app.routes.auth.verify_password', return_value=True), \
         patch('app.routes.auth.create_access_token', return_value=proper_token):
        user_data = {"email": test_email, "password": test_password}
        response = client.post("/auth/login", json=user_data)
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"
        access_token = response.json()["access_token"]
    
    # Mock for protected route step - find user by ID in the utils module
    mock_db["utils_db"]["users"].find_one.return_value = user_doc
    
    headers = {"Authorization": f"Bearer {access_token}"}
    response = client.get("/auth/protected-route", headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == f"Hello, {test_username}!"


@pytest.mark.asyncio
async def test_register_user(client: TestClient, mock_db):
    user_data = {"email": test_email, "name": test_username, "password": test_password, "role": test_role}  # Changed from "username" to "name" due to alias
    mock_db["auth_db"]["users"].find_one.return_value = None # Ensure user doesn't exist for registration
    mock_db["auth_db"]["users"].insert_one.return_value = type('obj', (object,), {'inserted_id' : 'some_id'})
    response = client.post("/auth/register", json=user_data)
    assert response.status_code == 201  # Changed from 200 to 201 as per the route definition
    assert "userId" in response.json()  # Changed from user_id to userId as per the actual response
    assert "token" in response.json()  # Check for token in response
    mock_db["auth_db"]["users"].insert_one.assert_called_once()

    # Test registering with the same email again
    user_data_same_email = {"email": test_email, "name": test_username, "password": test_password, "role": test_role}  # Changed from "username" to "name" due to alias
    mock_db["auth_db"]["users"].find_one.return_value = {"email": test_email} # Simulate existing user
    response = client.post("/auth/register", json=user_data_same_email)
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered."
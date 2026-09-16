import bcrypt
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from app.core.config import settings
from app.db_models import UsageMeter, User
from sqlmodel import select
from app.db import get_session
from app.core.context import set_clinic_id

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="v1/auth/login")

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

def verify_password(plain_password: str, hashed_password: str):
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_password_hash(password: str):
    # Salt is generated automatically by gensalt()
    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return pw_hash.decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def create_access_token_with_context(user: User, expires_delta: Optional[timedelta] = None):
    data = {
        "sub": user.username,
        "clinic_id": user.clinic_id
    }
    return create_access_token(data, expires_delta)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    with get_session() as session:
        user = session.exec(select(User).where(User.username == token_data.username)).first()
        if user is None:
            raise credentials_exception
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
            
        # Set Clinic Context
        if user.clinic_id:
            set_clinic_id(user.clinic_id)
            
        return user

async def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master Administrative privileges required"
        )
    return current_user

async def get_current_user_ws(token: str = None):
    """
    WebSocket-compatible authentication that accepts token from query parameters.
    """
    if token is None:
        return None
        
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        username: str = payload.get("sub")
        if username is None:
            return None
            
        with get_session() as session:
            user = session.exec(select(User).where(User.username == username)).first()
            if user and user.is_active:
                return user
    except JWTError:
        return None
    return None

async def get_current_clinic_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["clinic_admin", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clinic Administrative privileges required"
        )
    return current_user

def require_role(allowed_roles: list[str]):
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: {current_user.role} role does not have permission"
            )
        return current_user
    return role_checker

async def seed_initial_admin():
    """
    Industry Standard Seeding: Provisions the master administrator account 
    based on environment configuration during startup.
    """
    with get_session() as session:
        admin_exists = session.exec(select(User).where(User.role == "admin")).first()
        if not admin_exists:
            try:
                admin = User(
                    username=settings.initial_admin_username,
                    email=settings.initial_admin_email,
                    hashed_password=get_password_hash(settings.initial_admin_password),
                    role="admin",
                    full_name="Master Administrator",
                    is_active=True
                )
                session.add(admin)
                session.commit()
                print(f"🚀 Administrative Seed Successful: {settings.initial_admin_email} provisioned.")
            except Exception as e:
                print(f"⚠️ Administrative Seeding Protocol Failed: {str(e)}")
        else:
            print("✅ Administrative Integrity Verified: Master account exists.")

@router.post("/register", response_model=Token)
async def register(user_in: UserCreate):
    with get_session() as session:
        user_exists = session.exec(select(User).where(User.username == user_in.username)).first()
        if user_exists:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        email_exists = session.exec(select(User).where(User.email == user_in.email)).first()
        if email_exists:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Public registration strictly provisions the 'doctor' role
        role = "doctor"

        user = User(
            username=user_in.username,
            email=user_in.email,
            hashed_password=get_password_hash(user_in.password),
            full_name=user_in.full_name,
            role=role
        )
        session.add(user)
        session.flush() # Get user.id

        # Initialize Trial Usage Meter in PostgreSQL
        meter = UsageMeter(id=str(user.id))
        session.add(meter)
        session.commit()
        session.refresh(user)
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

class UserLogin(BaseModel):
    username: str
    email: EmailStr
    password: str

@router.post("/login")
async def login(login_in: UserLogin):
    with get_session() as session:
        user = session.exec(
            select(User).where(User.username == login_in.username, User.email == login_in.email)
        ).first()
        
    if not user or not verify_password(login_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username, email, or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": {
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        }
    }

@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

import cloudinary.uploader
from dotenv import load_dotenv
import os
from fastapi import Depends, FastAPI, HTTPException, status, BackgroundTasks, File, UploadFile, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import timedelta
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr

from . import crud, models, schemas
from database import SessionLocal, engine

load_dotenv()

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
REFRESH_TOKEN_EXPIRE_MINUTES = int(os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES"))
ALGORITHM = os.getenv("ALGORITHM")
SECRET_KEY = os.getenv("SECRET_KEY")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("EMAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("EMAIL_PASSWORD"),
    MAIL_FROM=os.getenv("EMAIL_USERNAME"),
    MAIL_PORT=int(os.getenv("EMAIL_PORT")),
    MAIL_SERVER=os.getenv("EMAIL_HOST"),
    MAIL_TLS=True,
    MAIL_SSL=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


app = FastAPI()
models.Base.metadata.create_all(bind=engine)


origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB

ALLOWED_FILE_TYPES = ["image/jpeg", "image/png"]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception
    user = crud.get_user_by_email(db, email=token_data.email)
    if user is None:
        raise credentials_exception
    return user


@app.post("/users/", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Email already registered")
    return crud.create_user(db=db, user=user)


@app.post("/users/send_verification_email/")
async def send_verification_email_endpoint(email: schemas.EmailSchema, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=email.email)
    if user is None or user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid email or already verified")
    crud.send_verification_email(email.email, db, background_tasks)
    return {"message": "Verification email sent"}


@app.get("/users/verify/{token}")
async def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        models.User.email_verification_token == token).first()
    if user is None or user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid token or already verified")
    user.is_verified = True
    db.commit()
    return {"message": "Email verified"}


@app.post("/token/", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud.authenticate_user_and_get_tokens(db, schemas.UserLogin(
        email=form_data.username, password=form_data.password))
    return user


@app.post("/users/avatar", response_model=schemas.User)
async def upload_avatar(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size too large")

    if file.content_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type")

    try:
        result = cloudinary.uploader.upload(file.file)
    except cloudinary.exceptions.CloudinaryError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error uploading file: {e}")

    current_user.avatar_url = result["secure_url"]
    db.commit()
    db.refresh(current_user)

    return current_user

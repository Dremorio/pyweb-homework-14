import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.models import User


# Налаштування тестової бази даних
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={
                       "check_same_thread": False})
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

# Залежність для тестування


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# Перевизначення залежності get_db для тестів
app.dependency_overrides[get_db] = override_get_db

# Фікстура для клієнта


@pytest.fixture()
def client():
    return TestClient(app)

# Тест створення контакту


def test_create_contact(client):
    # Створення тестового користувача
    user_data = {"email": "testuser@example.com", "password": "testpassword"}
    response = client.post("/users/", json=user_data)
    assert response.status_code == 201

    # Отримання токена для користувача
    login_data = {"username": "testuser@example.com",
                  "password": "testpassword"}
    response = client.post("/token/", data=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Створення контакту
    contact_data = {
        "first_name": "Test",
        "last_name": "Contact",
        "email": "testcontact@example.com",
        "phone_number": "1234567890",
        "birthday": "2000-01-01"
    }
    response = client.post(
        "/contacts/",
        json=contact_data,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201
    assert response.json()["first_name"] == contact_data["first_name"]

    # Перевірка помилки 401 Unauthorized (без токену)
    response = client.post("/contacts/", json=contact_data)
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}

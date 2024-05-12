from sqlalchemy import Boolean, Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from passlib.context import CryptContext
from database import Base

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    contacts = relationship("Contact", back_populates="owner")
    avatar_url = Column(String, nullable=True)
    role = Column(String, default="user")

    def verify_password(self, plain_password):
        return pwd_context.verify(plain_password, self.hashed_password)

    def can_view_contact(self, contact: "Contact") -> bool:
        return self.role == "admin" or contact.owner_id == self.id

    def can_edit_contact(self, contact: "Contact") -> bool:
        return self.role == "admin" or contact.owner_id == self.id

    def can_delete_contact(self, contact: "Contact") -> bool:
        return self.role == "admin" or contact.owner_id == self.id


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    phone_number = Column(String)
    birthday = Column(Date)
    additional_data = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="contacts")


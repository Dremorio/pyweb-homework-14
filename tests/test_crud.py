import unittest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from sqlalchemy import create_engine

from app import crud, schemas, models
from app.database import Base


class TestCRUD(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=cls.engine)
        cls.session = Session(bind=cls.engine)

    def setUp(self):
        self.session.rollback()
        self.user = models.User(
            id=1, email="test@example.com", role="user", hashed_password="hashed_password")
        self.user_admin = models.User(
            id=2, email="admin@example.com", role="admin", hashed_password="hashed_password")
        self.contact1 = models.Contact(id=1, first_name="John", last_name="Doe", email="johndoe@example.com",
                                       phone_number="1234567890", birthday=date(1990, 1, 1), owner_id=self.user.id)
        self.contact2 = models.Contact(id=2, first_name="Jane", last_name="Smith", email="janesmith@example.com",
                                       phone_number="9876543210", birthday=date(1985, 5, 15), owner_id=self.user.id)
        self.session.add_all(
            [self.user, self.user_admin, self.contact1, self.contact2])
        self.session.commit()

    @patch("app.crud.pwd_context.verify", return_value=True)
    def test_authenticate_user(self, mock_verify):
        user_data = schemas.UserLogin(
            email=self.user.email, password="correct_password")
        result = crud.authenticate_user(self.session, user_data)
        self.assertEqual(result, self.user)

    @patch("app.crud.pwd_context.verify", return_value=False)
    def test_authenticate_user_invalid_password(self, mock_verify):
        user_data = schemas.UserLogin(
            email=self.user.email, password="wrong_password")
        with self.assertRaises(HTTPException) as exc:
            crud.authenticate_user(self.session, user_data)
        self.assertEqual(exc.exception.status_code,
                         status.HTTP_401_UNAUTHORIZED)

    def test_get_contacts(self):
        contacts = crud.get_contacts(db=self.session, user_id=self.user.id)
        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0], self.contact1)
        self.assertEqual(contacts[1], self.contact2)

    def test_get_contacts_admin(self):
        contacts = crud.get_contacts(
            db=self.session, user_id=self.user_admin.id)
        self.assertEqual(len(contacts), 2)

    def test_get_contact(self):
        contact = crud.get_contact(
            db=self.session, contact_id=1, user_id=self.user.id)
        self.assertEqual(contact, self.contact1)

    def test_get_contact_not_found(self):
        with self.assertRaises(HTTPException) as exc:
            crud.get_contact(db=self.session, contact_id=3,
                             user_id=self.user.id)
        self.assertEqual(exc.exception.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_contact_wrong_user(self):
        with self.assertRaises(HTTPException) as exc:
            crud.get_contact(db=self.session, contact_id=1,
                             user_id=self.user_admin.id)
        self.assertEqual(exc.exception.status_code, status.HTTP_404_NOT_FOUND)

    @patch("app.crud.send_verification_email")
    def test_create_user(self, mock_send_email):
        user_data = schemas.UserCreate(
            email="newuser@example.com", password="new_password")
        user = crud.create_user(db=self.session, user=user_data)
        self.assertEqual(user.email, user_data.email)
        mock_send_email.assert_called_once()

    def test_create_user_duplicate_email(self):
        user_data = schemas.UserCreate(
            email=self.user.email, password="new_password")
        with self.assertRaises(HTTPException) as exc:
            crud.create_user(db=self.session, user=user_data)
        self.assertEqual(exc.exception.status_code, status.HTTP_409_CONFLICT)

    def test_create_contact(self):
        contact_data = schemas.ContactCreate(first_name="Alice", last_name="Johnson",
                                             email="alice@example.com", phone_number="5555555555", birthday=date(2000, 12, 25))
        contact = crud.create_contact(
            db=self.session, contact=contact_data, user_id=self.user.id)
        self.assertEqual(contact.first_name, contact_data.first_name)
        self.assertEqual(contact.owner_id, self.user.id)

    def test_update_contact(self):
        contact_update = schemas.ContactUpdate(first_name="Updated John")
        updated_contact = crud.update_contact(
            db=self.session, contact_id=1, contact=contact_update, user_id=self.user.id)
        self.assertEqual(updated_contact.first_name, "Updated John")

    def test_update_contact_not_found(self):
        contact_update = schemas.ContactUpdate(first_name="Updated John")
        with self.assertRaises(HTTPException):
            crud.update_contact(db=self.session, contact_id=3,
                                contact=contact_update, user_id=self.user.id)

    def test_update_contact_wrong_user(self):
        contact_update = schemas.ContactUpdate(first_name="Updated John")
        with self.assertRaises(HTTPException):
            crud.update_contact(db=self.session, contact_id=1,
                                contact=contact_update, user_id=self.user_admin.id)

    def test_delete_contact(self):
        deleted_contact = crud.delete_contact(
            db=self.session, contact_id=1, user_id=self.user.id)
        self.assertEqual(deleted_contact, self.contact1)
        self.assertIsNone(self.session.query(
            models.Contact).filter(models.Contact.id == 1).first())

    def test_delete_contact_not_found(self):
        with self.assertRaises(HTTPException):
            crud.delete_contact(
                db=self.session, contact_id=3, user_id=self.user.id)

    def test_delete_contact_wrong_user(self):
        with self.assertRaises(HTTPException):
            crud.delete_contact(db=self.session, contact_id=1,
                                user_id=self.user_admin.id)

    def test_search_contacts(self):
        contacts = crud.search_contacts(
            db=self.session, query="John", user_id=self.user.id)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0], self.contact1)

    def test_get_contacts_with_upcoming_birthdays(self):
        today = date.today()
        next_week = today + timedelta(days=7)
        contacts = crud.get_contacts_with_upcoming_birthdays(
            db=self.session, user_id=self.user.id)
        # No birthdays in the next week in the test data
        self.assertEqual(len(contacts), 0)


if __name__ == '__main__':
    unittest.main()

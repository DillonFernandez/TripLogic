import firebase_admin
from firebase_admin import credentials, firestore

from app.config import get_settings


def initialize_firebase() -> firebase_admin.App:
    """Initialize Firebase Admin once and return the active app."""

    try:
        return firebase_admin.get_app()
    except ValueError:
        settings = get_settings()

        firebase_credential = credentials.Certificate(
            str(settings.firebase_credentials_path)
        )

        return firebase_admin.initialize_app(firebase_credential)


firebase_app = initialize_firebase()

firestore_db = firestore.client(app=firebase_app)

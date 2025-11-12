import os
from typing import Optional
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from app.config import settings

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service():
    """Authenticates with Google Drive and returns the service object."""
    try:
        credentials = Credentials.from_service_account_file(
            settings.GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=SCOPES
        )
        service = build('drive', 'v3', credentials=credentials)
        return service
    except Exception as e:
        print(f"Error authenticating with Google Drive: {e}")
        return None

async def upload_file_to_drive(file_path: str, file_name: str, mime_type: str) -> Optional[str]:
    """Uploads a file to Google Drive and returns its file ID."""
    service = get_drive_service()
    if not service:
        return None

    file_metadata = {'name': file_name}
    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    
    try:
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')
    except Exception as e:
        print(f"Error uploading file to Google Drive: {e}")
        return None
"""Google Drive document parsing and syncing."""
from __future__ import annotations

import json
from typing import Optional
from urllib.parse import urlparse

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import settings
from services.ai_service import ai_service
from services.db_service import db_service


class DriveService:
    def __init__(self, credentials_json: str) -> None:
        self.credentials_json = credentials_json

    def _build_docs_client(self):
        creds = None
        if self.credentials_json:
            try:
                creds_dict = json.loads(self.credentials_json)
                creds = Credentials.from_service_account_info(
                    creds_dict, scopes=["https://www.googleapis.com/auth/documents.readonly"]
                )
                return build("docs", "v1", credentials=creds, cache_discovery=False)
            except Exception:
                return None
        return None

    def _parse_doc_id(self, url_or_id: str) -> str:
        parsed = urlparse(url_or_id)
        if parsed.scheme and "/d/" in parsed.path:
            return parsed.path.split("/d/")[-1].split("/")[0]
        return url_or_id

    def fetch_document_text(self, url_or_id: str) -> Optional[str]:
        doc_id = self._parse_doc_id(url_or_id)
        docs_client = self._build_docs_client()
        if not docs_client:
            return None
        try:
            doc = docs_client.documents().get(documentId=doc_id).execute()
            body = doc.get("body", {}).get("content", [])
            paragraphs = []
            for value in body:
                elements = value.get("paragraph", {}).get("elements", [])
                for element in elements:
                    text_run = element.get("textRun", {})
                    content = text_run.get("content")
                    if content:
                        paragraphs.append(content)
            return "\n".join(paragraphs)
        except Exception:
            return None

    async def sync_document(self, project_id: str, url_or_id: str) -> bool:
        document_text = self.fetch_document_text(url_or_id)
        if not document_text:
            return False
        assumptions = await ai_service.extract_assumptions(document_text)
        if not assumptions:
            return False
        await db_service.upsert_assumptions(project_id, assumptions)
        return True


drive_service = DriveService(settings.google_credentials)

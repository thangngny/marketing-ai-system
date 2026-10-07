from __future__ import annotations

from typing import Any

from ..constants import Impact
from .base import BaseConnector, Capability


class GoogleDriveConnector(BaseConnector):
    name = "google_drive"
    required_env = ("GOOGLE_DRIVE_CLIENT_ID", "GOOGLE_DRIVE_CLIENT_SECRET", "GOOGLE_DRIVE_REFRESH_TOKEN")

    def __init__(self, settings):
        super().__init__(settings)
        self._cached_access_token: str | None = None

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="upload_shared_file", impact=Impact.DRAFT,
                       note="Uploads an artifact to Google Drive and creates a shareable view link."),
            Capability(name="search_files", impact=Impact.READ, live_ready=True,
                       note="Search Google Drive by file name or type."),
            Capability(name="read_file", impact=Impact.READ, live_ready=True,
                       note="Read text/CSV/content from a Google Drive file, doc, or sheet."),
        ]

    def _access_token(self) -> str:
        if self._cached_access_token:
            return self._cached_access_token
        response = self.request(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": self.env("GOOGLE_DRIVE_CLIENT_ID"),
                "client_secret": self.env("GOOGLE_DRIVE_CLIENT_SECRET"),
                "refresh_token": self.env("GOOGLE_DRIVE_REFRESH_TOKEN"),
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
        response.raise_for_status()
        self._cached_access_token = str(response.json()["access_token"])
        return self._cached_access_token

    def probe_live(self) -> tuple[bool, str]:
        response = self.request(
            "GET",
            "https://www.googleapis.com/drive/v3/about",
            params={"fields": "user"},
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=15.0,
        )
        return response.is_success, f"Google Drive /about probe returned HTTP {response.status_code}."

    def upload_shared_file(self, remote_path: str, content: bytes) -> dict[str, Any]:
        """Upload a small artifact to the connected account's Google Drive and return a
        shareable view link (anyone with the link can view), so colleagues can open it
        without touching this machine or having Drive access to anything else.
        """
        token = self._access_token()
        import json as _json

        metadata = {"name": remote_path}
        files = {
            "metadata": (None, _json.dumps(metadata), "application/json"),
            "file": (remote_path, content, "application/octet-stream"),
        }
        response = self.request(
            "POST",
            "https://www.googleapis.com/upload/drive/v3/files",
            params={"uploadType": "multipart", "fields": "id,webViewLink"},
            headers={"Authorization": f"Bearer {token}"},
            files=files,
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        file_id = body["id"]
        self.request(
            "POST",
            f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "reader", "type": "anyone"},
            timeout=20.0,
        )
        return {"item_id": file_id, "web_url": body.get("webViewLink"), "path": remote_path}

    def search_files(self, query: str = "", limit: int = 20, mime_type: str | None = None) -> list[dict[str, Any]]:
        token = self._access_token()
        clauses = ["trashed = false"]
        if query:
            clean_q = query.replace("'", "\\'")
            clauses.append(f"name contains '{clean_q}'")
        if mime_type:
            clauses.append(f"mimeType = '{mime_type}'")
        q_str = " and ".join(clauses)
        response = self.request(
            "GET",
            "https://www.googleapis.com/drive/v3/files",
            params={
                "q": q_str,
                "pageSize": min(max(limit, 1), 50),
                "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink,description)",
                "orderBy": "modifiedTime desc",
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json().get("files", [])

    def read_file_content(self, file_id: str, max_chars: int = 50000) -> dict[str, Any]:
        token = self._access_token()
        meta_resp = self.request(
            "GET",
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            params={"fields": "id,name,mimeType,size,webViewLink"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        mime = meta.get("mimeType", "")
        name = meta.get("name", "")

        if mime == "application/vnd.google-apps.document":
            export_resp = self.request(
                "GET",
                f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                params={"mimeType": "text/plain"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=25.0,
            )
            export_resp.raise_for_status()
            content = export_resp.text
        elif mime == "application/vnd.google-apps.spreadsheet":
            export_resp = self.request(
                "GET",
                f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                params={"mimeType": "text/csv"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=25.0,
            )
            export_resp.raise_for_status()
            content = export_resp.text
        elif mime.startswith("text/") or mime in ("application/json", "application/xml", "application/javascript"):
            file_resp = self.request(
                "GET",
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params={"alt": "media"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=25.0,
            )
            file_resp.raise_for_status()
            content = file_resp.text
        else:
            content = f"[File: {name} (MIME: {mime}, Size: {meta.get('size', 'N/A')} bytes). Link: {meta.get('webViewLink')}]"

        truncated = len(content) > max_chars
        return {
            "id": file_id,
            "name": name,
            "mime_type": mime,
            "web_url": meta.get("webViewLink"),
            "content": content[:max_chars] if truncated else content,
            "truncated": truncated,
            "total_chars": len(content),
        }


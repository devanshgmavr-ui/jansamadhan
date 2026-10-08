"""Supabase Storage provider. Backend-only: the service-role key never
leaves the server, is never logged, and never appears in responses.

Bucket layout (private bucket, default "attachments"):
    problem-attachments/{problem_ticket}/{uuid}.{ext}
    solution-pdfs/{solution_ticket}/{uuid}.{ext}

Uploads use POST /storage/v1/object/{bucket}/{path}. Downloads create a
short-lived signed URL (POST .../object/sign/..., expiresIn 300s) and the
backend fetches the bytes server-side, so the key and the URL never reach
the frontend. Deletes use DELETE /storage/v1/object/{bucket}.

No new third-party dependency: plain stdlib HTTPS, same pattern as the
Brevo provider.
"""

import json
import logging
import urllib.error
import urllib.request

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

SIGNED_URL_TTL_SECONDS = 300


class StorageError(HTTPException):
    """Generic storage failure. Never carries credentials or internals."""


def _storage_root(base_url: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    if root.endswith("/rest/v1"):
        root = root[: -len("/rest/v1")]
    return root


class SupabaseStorageProvider:
    """Object-store provider speaking Supabase Storage over HTTPS."""

    name = "supabase"

    def __init__(self, base_url: str, service_key: str,
                 bucket: str = "attachments") -> None:
        if not (base_url or "").strip() or not (service_key or "").strip():
            raise StorageError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage is not configured.",
            )
        self._root = _storage_root(base_url)
        self._key = service_key
        self._bucket = (bucket or "attachments").strip() or "attachments"

    # -- low-level ---------------------------------------------------------
    def _headers(self, content_type: str | None = None) -> dict:
        headers = {
            "apikey": self._key,
            "Authorization": "Bearer " + self._key,
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _call(self, method: str, path: str, *,
              body: bytes | None = None,
              content_type: str | None = None,
              not_found_detail: str = "Attachment not found.") -> bytes:
        req = urllib.request.Request(
            self._root + path, data=body, method=method,
            headers=self._headers(content_type),
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                if not isinstance(raw, (bytes, bytearray)):
                    raw = b""
                return bytes(raw)
        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                err_body = ""
            # Supabase answers missing objects with HTTP 400 carrying an
            # embedded statusCode 404 / NoSuchKey marker.
            if exc.code == 404 or (
                exc.code == 400 and "NoSuchKey" in err_body
            ):
                raise StorageError(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=not_found_detail,
                ) from None
            logger.warning("Supabase storage failed: HTTP %s", exc.code)
            raise StorageError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Storage error. Please retry.",
            ) from None
        except Exception:
            logger.warning("Supabase storage failed: network error")
            raise StorageError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Storage error. Please retry.",
            ) from None

    # -- StorageProvider interface ------------------------------------------
    @staticmethod
    def object_path(*, namespace: str, ticket: str, stored_name: str) -> str:
        return f"{namespace}/{ticket}/{stored_name}"

    def save(self, *, ext: str, content: bytes, namespace: str,
             ticket: str) -> str:
        import uuid as _uuid

        stored_name = f"{_uuid.uuid4().hex}{ext}"
        self.upload_existing(namespace=namespace, ticket=ticket,
                             stored_name=stored_name, content=content)
        return stored_name

    def exists(self, *, namespace: str, ticket: str,
               stored_name: str) -> bool:
        try:
            self.read_bytes(namespace=namespace, ticket=ticket,
                            stored_name=stored_name)
            return True
        except StorageError as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                return False
            raise

    def upload_existing(self, *, namespace: str, ticket: str,
                        stored_name: str, content: bytes) -> str:
        """Upload bytes under an exact existing stored name (migration
        utility). Returns 'uploaded' or 'present'."""
        if self.exists(namespace=namespace, ticket=ticket,
                       stored_name=stored_name):
            return "present"
        path = self.object_path(namespace=namespace, ticket=ticket,
                                stored_name=stored_name)
        self._call(
            "POST",
            f"/storage/v1/object/{self._bucket}/{path}",
            body=content,
            content_type="application/octet-stream",
            not_found_detail="Storage error. Please retry.",
        )
        return "uploaded"

    def create_signed_url(self, *, namespace: str, ticket: str,
                          stored_name: str,
                          expires_in: int = SIGNED_URL_TTL_SECONDS) -> str:
        path = self.object_path(namespace=namespace, ticket=ticket,
                                stored_name=stored_name)
        raw = self._call(
            "POST",
            f"/storage/v1/object/sign/{self._bucket}/{path}",
            body=json.dumps({"expiresIn": expires_in}).encode("utf-8"),
            content_type="application/json",
        )
        try:
            signed = json.loads(raw.decode("utf-8")).get("signedURL", "")
        except (ValueError, AttributeError):
            signed = ""
        if not signed:
            raise StorageError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Storage error. Please retry.",
            )
        if signed.startswith("http"):
            return signed
        # Signed paths are relative to the Storage API root, not the
        # project root.
        return self._root + "/storage/v1" + signed

    def read_bytes(self, *, namespace: str, ticket: str,
                   stored_name: str) -> bytes:
        signed_url = self.create_signed_url(
            namespace=namespace, ticket=ticket, stored_name=stored_name)
        req = urllib.request.Request(signed_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
                return bytes(data) if isinstance(data, (bytes, bytearray)) else b""
        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                err_body = ""
            if exc.code == 404 or (
                exc.code == 400 and "NoSuchKey" in err_body
            ):
                raise StorageError(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Attachment not found.",
                ) from None
            logger.warning("Supabase storage failed: HTTP %s", exc.code)
            raise StorageError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Storage error. Please retry.",
            ) from None
        except Exception:
            logger.warning("Supabase storage failed: network error")
            raise StorageError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Storage error. Please retry.",
            ) from None

    def delete(self, *, namespace: str, ticket: str,
               stored_name: str) -> None:
        path = self.object_path(namespace=namespace, ticket=ticket,
                                stored_name=stored_name)
        try:
            self._call(
                "DELETE",
                f"/storage/v1/object/{self._bucket}",
                body=json.dumps({"prefixes": [path]}).encode("utf-8"),
                content_type="application/json",
            )
        except StorageError as exc:
            # Deleting a missing object is a no-op for callers.
            if exc.status_code != status.HTTP_404_NOT_FOUND:
                raise

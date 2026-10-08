"""File storage abstraction. Local provider for development; Supabase
Storage provider selected with STORAGE_PROVIDER=supabase. Future
object-store providers implement StorageProvider without touching
callers. Internal paths and object keys never leave this module."""

import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from fastapi import HTTPException, status

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".csv"}

# Minimal magic-number sniffing (pure stdlib) for common binary types.
_MAGIC = {
    ".pdf": [b"%PDF"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
}


NAMESPACE_PROBLEM_ATTACHMENTS = "problem-attachments"
NAMESPACE_SOLUTION_PDFS = "solution-pdfs"


class StorageProvider(Protocol):
    """save() returns the stored name (uuid + extension). The database
    keeps that name plus its own metadata; the provider maps it to a
    location (local filename or namespaced object path)."""

    def save(self, *, ext: str, content: bytes, namespace: str,
             ticket: str) -> str: ...
    def read_bytes(self, *, namespace: str, ticket: str,
                   stored_name: str) -> bytes: ...
    def delete(self, *, namespace: str, ticket: str,
               stored_name: str) -> None: ...


class LocalStorageProvider:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, *, ext: str, content: bytes, namespace: str,
             ticket: str) -> str:
        stored = f"{uuid.uuid4().hex}{ext}"
        dest = self.base_dir / stored
        # Generated name cannot traverse, but resolve defensively anyway.
        if dest.resolve().parent != self.base_dir.resolve():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage error.",
            )
        dest.write_bytes(content)
        return stored

    def read_bytes(self, *, namespace: str, ticket: str,
                   stored_name: str) -> bytes:
        return self.path_of(stored_name).read_bytes()

    def path_of(self, stored_name: str) -> Path:
        candidate = (self.base_dir / stored_name).resolve()
        if candidate.parent != self.base_dir.resolve() or not candidate.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found."
            )
        return candidate

    def delete(self, *, namespace: str, ticket: str,
               stored_name: str) -> None:
        try:
            self.path_of(stored_name).unlink(missing_ok=True)
        except HTTPException:
            pass


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


_provider: StorageProvider | None = None
_solution_provider: StorageProvider | None = None


def _select_provider() -> StorageProvider:
    from app.core.config import settings

    if (settings.STORAGE_PROVIDER or "").strip().lower() == "supabase":
        from app.services.supabase_storage import SupabaseStorageProvider

        return SupabaseStorageProvider(
            base_url=settings.SUPABASE_URL,
            service_key=settings.SUPABASE_SERVICE_ROLE_KEY,
            bucket=settings.SUPABASE_ATTACHMENTS_BUCKET,
        )
    return LocalStorageProvider(_backend_root() / "uploads" / "problem_attachments")


def _select_solution_provider() -> StorageProvider:
    from app.core.config import settings

    if (settings.STORAGE_PROVIDER or "").strip().lower() == "supabase":
        from app.services.supabase_storage import SupabaseStorageProvider

        return SupabaseStorageProvider(
            base_url=settings.SUPABASE_URL,
            service_key=settings.SUPABASE_SERVICE_ROLE_KEY,
            bucket=settings.SUPABASE_ATTACHMENTS_BUCKET,
        )
    return LocalStorageProvider(_backend_root() / "uploads" / "solution_pdfs")


def get_provider() -> StorageProvider:
    global _provider
    if _provider is None:
        _provider = _select_provider()
    return _provider


def get_solution_provider() -> StorageProvider:
    global _solution_provider
    if _solution_provider is None:
        _solution_provider = _select_solution_provider()
    return _solution_provider


def reset_providers() -> None:
    """Test hook: drop cached providers so STORAGE_PROVIDER switches apply."""
    global _provider, _solution_provider
    _provider = None
    _solution_provider = None


MAX_SOLUTION_PDF_BYTES = 15 * 1024 * 1024


def validate_solution_pdf(filename: str, content: bytes) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only PDF files are accepted for the solution document.",
        )
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Empty file uploads are not allowed.",
        )
    if len(content) > MAX_SOLUTION_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF exceeds the 15 MB limit.",
        )
    if not content.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File content is not a valid PDF.",
        )
    return ext


def sanitize_original_name(name: str | None) -> str:
    """Display-only filename: strip directories and control characters."""
    if not name:
        return "attachment"
    base = name.replace("\\", "/").split("/")[-1].strip()
    base = "".join(c for c in base if c.isprintable()).strip(" .")
    return (base or "attachment")[:255]


def validate_attachment(filename: str, content: bytes, content_type: str | None) -> str:
    """Return the safe lowercase extension, or raise 422/413."""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type not allowed. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Empty file uploads are not allowed.",
        )
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 10 MB limit.",
        )
    for prefix in _MAGIC.get(ext, []):
        if not content.startswith(prefix):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File content does not match its extension.",
            )
    return ext


def sniff_mime(ext: str, declared: str | None) -> str:
    defaults = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".txt": "text/plain",
        ".csv": "text/csv",
    }
    if declared and "/" in declared and len(declared) <= 100:
        # Trust only a plausible declared type for the allowed families.
        family = declared.split("/")[0]
        if family in ("image", "text") or declared == "application/pdf":
            return declared
    return defaults.get(ext, "application/octet-stream")


def open_stream(stored_name: str) -> BinaryIO:
    return get_provider().path_of(stored_name).open("rb")

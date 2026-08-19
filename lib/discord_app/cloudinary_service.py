from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import secrets
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .storage import ControlStore


CLOUD_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,128}$")
API_KEY_RE = re.compile(r"^[0-9A-Za-z_-]{6,128}$")
SAFE_ASSET_RE = re.compile(r"^[A-Za-z0-9._-]{1,255}$")
SUPPORTED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg"})


class CloudinaryError(RuntimeError):
    def __init__(self, public_message: str, code: str = "cloudinary_error", internal: str = ""):
        super().__init__(public_message)
        self.public_message = public_message
        self.code = code
        self.internal = internal


@dataclass(frozen=True, slots=True)
class CloudinarySnapshot:
    cloud_name: str
    api_key: str
    api_secret: str
    folder: str

    @property
    def configured(self) -> bool:
        return bool(self.cloud_name and self.api_key and self.api_secret)


class CloudinaryService:
    """Server-side Cloudinary adapter.

    API secret material remains in the encrypted control store/bootstrap
    environment. Browser code receives only same-origin image URLs; uploads and
    Admin API tests are performed by the Flask backend.
    """

    def __init__(self, store: ControlStore):
        self.store = store
        self._env_cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
        self._env_api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
        self._env_api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()
        self._env_folder = os.getenv("CLOUDINARY_FOLDER", "discord-ui").strip() or "discord-ui"

    @property
    def cloud_name(self) -> str:
        return (self.store.get_secret("CLOUDINARY_CLOUD_NAME") or self._env_cloud_name).strip()

    @property
    def api_key(self) -> str:
        return (self.store.get_secret("CLOUDINARY_API_KEY") or self._env_api_key).strip()

    @property
    def api_secret(self) -> str:
        return (self.store.get_secret("CLOUDINARY_API_SECRET") or self._env_api_secret).strip()

    @property
    def folder(self) -> str:
        value = (self.store.get_secret("CLOUDINARY_FOLDER") or self._env_folder).strip().strip("/")
        return value or "discord-ui"

    @property
    def configured(self) -> bool:
        return self.snapshot().configured

    def snapshot(self) -> CloudinarySnapshot:
        cloud_name = self.validate_cloud_name(self.cloud_name) if self.cloud_name else ""
        api_key = self.validate_api_key(self.api_key) if self.api_key else ""
        api_secret = self.validate_api_secret(self.api_secret) if self.api_secret else ""
        folder = self.validate_folder(self.folder)
        return CloudinarySnapshot(cloud_name, api_key, api_secret, folder)

    @staticmethod
    def validate_cloud_name(value: str) -> str:
        value = (value or "").strip()
        if not CLOUD_NAME_RE.fullmatch(value):
            raise ValueError("Cloud name do Cloudinary inválido.")
        return value

    @staticmethod
    def validate_api_key(value: str) -> str:
        value = (value or "").strip()
        if not API_KEY_RE.fullmatch(value):
            raise ValueError("API key do Cloudinary inválida.")
        return value

    @staticmethod
    def validate_api_secret(value: str) -> str:
        value = (value or "").strip()
        if not (8 <= len(value) <= 4096) or any(ord(ch) < 32 for ch in value):
            raise ValueError("API secret do Cloudinary inválida.")
        return value

    @staticmethod
    def validate_folder(value: str) -> str:
        value = (value or "discord-ui").strip().strip("/")
        if not value or len(value) > 200:
            raise ValueError("Pasta do Cloudinary inválida.")
        parts = value.split("/")
        if any(not SAFE_ASSET_RE.fullmatch(part) for part in parts):
            raise ValueError("Pasta do Cloudinary inválida.")
        return value

    def save_partial(
        self,
        *,
        admin_id: Optional[int],
        cloud_name: str = "",
        api_key: str = "",
        api_secret: str = "",
        folder: str = "",
    ) -> list[str]:
        changed: list[str] = []
        if cloud_name:
            self.store.set_secret("CLOUDINARY_CLOUD_NAME", self.validate_cloud_name(cloud_name), admin_id)
            changed.append("CLOUDINARY_CLOUD_NAME")
        if api_key:
            self.store.set_secret("CLOUDINARY_API_KEY", self.validate_api_key(api_key), admin_id)
            changed.append("CLOUDINARY_API_KEY")
        if api_secret:
            self.store.set_secret("CLOUDINARY_API_SECRET", self.validate_api_secret(api_secret), admin_id)
            changed.append("CLOUDINARY_API_SECRET")
        if folder:
            self.store.set_secret("CLOUDINARY_FOLDER", self.validate_folder(folder), admin_id)
            changed.append("CLOUDINARY_FOLDER")
        return changed

    def _basic_auth_header(self) -> str:
        snap = self.snapshot()
        if not snap.configured:
            raise CloudinaryError("Cloudinary não configurado.", "not_configured")
        encoded = base64.b64encode(f"{snap.api_key}:{snap.api_secret}".encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"

    def delivery_url(self, filename: str) -> str:
        snap = self.snapshot()
        if not snap.configured:
            raise CloudinaryError("Cloudinary não configurado.", "not_configured")
        name = Path(filename).name
        suffix = Path(name).suffix.lower()
        if name != filename or not SAFE_ASSET_RE.fullmatch(name) or suffix not in SUPPORTED_IMAGE_SUFFIXES:
            raise CloudinaryError("Asset de imagem inválido.", "invalid_asset")
        stem = Path(name).stem
        public_path = "/".join([snap.folder, stem])
        quoted_public_path = "/".join(urllib.parse.quote(part, safe="-_.~") for part in public_path.split("/"))
        return f"https://res.cloudinary.com/{urllib.parse.quote(snap.cloud_name, safe='-_.~')}/image/upload/{quoted_public_path}{suffix}"

    def test_connection(self, timeout: int = 8) -> tuple[bool, str]:
        snap = self.snapshot()
        if not snap.configured:
            return False, "Cloudinary não configurado."
        url = f"https://api.cloudinary.com/v1_1/{urllib.parse.quote(snap.cloud_name, safe='-_.~')}/config"
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"Accept": "application/json", "Authorization": self._basic_auth_header(), "User-Agent": "discord-cloudinary-admin/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=max(1, int(timeout)), context=ssl.create_default_context()) as response:
                body = json.loads(response.read(256 * 1024).decode("utf-8"))
            if not isinstance(body, dict):
                return False, "Resposta Admin API inválida."
            return True, "Admin API autenticada."
        except urllib.error.HTTPError as exc:
            return False, f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            return False, reason.__class__.__name__ if reason else "URLError"
        except Exception as exc:
            return False, exc.__class__.__name__

    @staticmethod
    def _multipart(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
        boundary = f"----app-cloudinary-{secrets.token_hex(16)}"
        out = bytearray()
        for name, value in fields.items():
            out.extend(f"--{boundary}\r\n".encode())
            out.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            out.extend(str(value).encode("utf-8"))
            out.extend(b"\r\n")
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        out.extend(f"--{boundary}\r\n".encode())
        out.extend(f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode())
        out.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
        out.extend(file_path.read_bytes())
        out.extend(b"\r\n")
        out.extend(f"--{boundary}--\r\n".encode())
        return bytes(out), f"multipart/form-data; boundary={boundary}"

    def upload_file(self, path: Path, *, overwrite: bool = False, timeout: int = 30) -> dict[str, Any]:
        snap = self.snapshot()
        if not snap.configured:
            raise CloudinaryError("Cloudinary não configurado.", "not_configured")
        path = path.resolve()
        suffix = path.suffix.lower()
        if not path.is_file() or suffix not in SUPPORTED_IMAGE_SUFFIXES or not SAFE_ASSET_RE.fullmatch(path.name):
            raise CloudinaryError("Arquivo de imagem inválido.", "invalid_asset")
        if path.stat().st_size > 25 * 1024 * 1024:
            raise CloudinaryError("Arquivo excede o limite local de migração.", "asset_too_large")
        public_id = f"{snap.folder}/{path.stem}"
        body, content_type = self._multipart({
            "public_id": public_id,
            "overwrite": "true" if overwrite else "false",
            "unique_filename": "false",
            "invalidate": "true" if overwrite else "false",
        }, path)
        url = f"https://api.cloudinary.com/v1_1/{urllib.parse.quote(snap.cloud_name, safe='-_.~')}/image/upload"
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": self._basic_auth_header(),
                "Content-Type": content_type,
                "User-Agent": "discord-cloudinary-migrator/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=max(1, int(timeout)), context=ssl.create_default_context()) as response:
                result = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(64 * 1024).decode("utf-8", "replace")[:500]
            except Exception:
                pass
            raise CloudinaryError("Falha no upload para Cloudinary.", f"http_{exc.code}", detail) from exc
        except Exception as exc:
            raise CloudinaryError("Falha no upload para Cloudinary.", exc.__class__.__name__) from exc
        if not isinstance(result, dict) or not result.get("public_id"):
            raise CloudinaryError("Resposta de upload inválida.", "invalid_response")
        return {
            "public_id": str(result.get("public_id") or ""),
            "format": str(result.get("format") or suffix.lstrip(".")),
            "bytes": int(result.get("bytes") or path.stat().st_size),
            "secure_url": str(result.get("secure_url") or ""),
        }

    def migrate_directory(self, directory: Path, *, overwrite: bool = False) -> dict[str, Any]:
        directory = directory.resolve()
        if not directory.is_dir():
            raise CloudinaryError("Diretório local de imagens não encontrado.", "image_directory_missing")
        files = sorted(
            path for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES and SAFE_ASSET_RE.fullmatch(path.name)
        )
        succeeded: list[str] = []
        failed: list[dict[str, str]] = []
        for path in files:
            try:
                self.upload_file(path, overwrite=overwrite)
                succeeded.append(path.name)
            except CloudinaryError as exc:
                failed.append({"file": path.name, "code": exc.code})
        return {"total": len(files), "succeeded": len(succeeded), "failed": failed, "files": succeeded}

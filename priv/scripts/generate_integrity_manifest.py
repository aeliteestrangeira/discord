from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "HASHES.sha256"

EXCLUDED_DIRS = {
    ".git", ".venv", ".runtime", "instance", "node_modules", "out", "build", ".pytest_cache", "__pycache__",
}
EXCLUDED_FILES = {
    ".env",
    "config/.env",
    "config/SUPABASE_PRIVILEGED.env",
    "HASHES.sha256",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}


def is_public_manifest_path(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    posix = relative.as_posix()
    if posix in EXCLUDED_FILES:
        return False
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return path.is_file()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    entries = []
    for path in sorted(ROOT.rglob("*"), key=lambda item: item.relative_to(ROOT).as_posix().lower()):
        if not is_public_manifest_path(path):
            continue
        relative = path.relative_to(ROOT).as_posix()
        entries.append(f"{sha256(path)}  {relative}")
    MANIFEST.write_text("\n".join(entries) + "\n", encoding="utf-8")
    print(f"Manifesto publico gerado: {len(entries)} arquivos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

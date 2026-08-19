from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parent
manifest = ROOT / "HASHES.sha256"

LF_TEXT_SUFFIXES = {
    ".html", ".css", ".js", ".cjs", ".py", ".json", ".yml", ".yaml",
    ".md", ".txt", ".sql", ".ps1", ".svg", ".example",
}
LF_TEXT_NAMES = {".gitattributes", ".gitignore"}
CRLF_TEXT_SUFFIXES = {".bat"}


def canonical_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix not in LF_TEXT_SUFFIXES and suffix not in CRLF_TEXT_SUFFIXES and path.name not in LF_TEXT_NAMES:
        return data
    # Normalize CRLF and lone CR first, then apply the repository EOL policy.
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if suffix in CRLF_TEXT_SUFFIXES:
        data = data.replace(b"\n", b"\r\n")
    return data


def sha256(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()


errors = 0
for raw in manifest.read_text(encoding="utf-8").splitlines():
    if not raw.strip():
        continue
    expected, rel = raw.split("  ", 1)
    path = ROOT / rel
    if not path.is_file():
        print(f"MISSING  {rel}")
        errors += 1
        continue
    actual = sha256(path)
    if actual != expected:
        print(f"FAIL     {rel}")
        errors += 1
    else:
        print(f"OK       {rel}")

sys.exit(1 if errors else 0)

from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parent
manifest = ROOT / "HASHES.sha256"

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

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

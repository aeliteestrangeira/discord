from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC_PAGES = ROOT / "priv" / "static" / "pages"
STATIC_FONTS = ROOT / "priv" / "static" / "fonts"
STATIC_ASSETS = ROOT / "priv" / "static" / "assets"
ASSET_CSS = ROOT / "assets" / "css"
ASSET_JS = ROOT / "assets" / "js"

PAGE_MAP = {
    "index.html": "login.html",
    "login.html": "login.html",
    "register.html": "register.html",
    "channels.html": "channels.html",
    "guild.html": "guild.html",
}

# The canonical captures intentionally keep their original relative image paths.
# Flask resolves these through the pinned Cloudinary fallback. Pages has no Flask,
# so only the generated deployment copy rewrites those paths. Source HTML remains
# byte-for-byte unchanged and is verified separately by test_architecture.py.
PINNED_IMAGE_URLS = {
    "0082-d8680b1c1576ecc8.svg": "https://res.cloudinary.com/do7vwsnpg/image/upload/v1787132568/0082-d8680b1c1576ecc8_rrwlpk.svg",
    "0083-131c318dd45b7aa4.svg": "https://res.cloudinary.com/do7vwsnpg/image/upload/v1787132569/0083-131c318dd45b7aa4_i9zgvc.svg",
    "login-qr-icon.png": "https://res.cloudinary.com/do7vwsnpg/image/upload/v1787132569/login-qr-icon_cxxqbn.png",
}

FROZEN_SOURCE_PATHS = [
    "priv/static/pages/login.html",
    "priv/static/pages/register.html",
    "priv/static/pages/channels.html",
    "priv/static/pages/guild.html",
    "assets/css/discord.css",
    "assets/css/captcha.css",
    "assets/css/channels.css",
    "assets/css/guild.css",
    "assets/css/admin.css",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_commit() -> str:
    value = str(os.getenv("GITHUB_SHA") or "").strip()
    if value:
        return value
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def copy_tree_contents(source: Path, destination: Path) -> None:
    if not source.is_dir():
        return
    for item in sorted(source.rglob("*"), key=lambda p: p.relative_to(source).as_posix().lower()):
        if not item.is_file():
            continue
        target = destination / item.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def pages_html(source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    for name, url in PINNED_IMAGE_URLS.items():
        text = text.replace(f'src="images/{name}"', f'src="{url}"')
    return text


def build(output: Path) -> None:
    output = output.resolve()
    if output == ROOT:
        raise SystemExit("ABORTADO: output do Pages nao pode ser a raiz do repositorio.")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / ".nojekyll").write_text("", encoding="utf-8")

    for destination, source_name in PAGE_MAP.items():
        source = STATIC_PAGES / source_name
        if not source.is_file():
            raise SystemExit(f"ABORTADO: pagina canonica ausente: {source_name}")
        (output / destination).write_text(pages_html(source), encoding="utf-8", newline="\n")

    copy_tree_contents(ASSET_CSS, output)
    copy_tree_contents(ASSET_JS, output)
    copy_tree_contents(STATIC_FONTS, output / "fonts")
    copy_tree_contents(STATIC_ASSETS, output / "assets")

    frozen = {name: sha256(ROOT / name) for name in FROZEN_SOURCE_PATHS}
    build_info = {
        "artifact": "github-pages-direct-app",
        "sourceCommit": source_commit(),
        "canonicalUi": "priv/static/pages + assets/css + assets/js",
        "frozenSourceSha256": frozen,
    }
    (output / "BUILD_INFO.json").write_text(
        json.dumps(build_info, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    manifest_entries = []
    for path in sorted(output.rglob("*"), key=lambda p: p.relative_to(output).as_posix().lower()):
        if not path.is_file() or path.name == "PAGES_SHA256.txt":
            continue
        manifest_entries.append(f"{sha256(path)}  {path.relative_to(output).as_posix()}")
    (output / "PAGES_SHA256.txt").write_text(
        "\n".join(manifest_entries) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"GitHub Pages artifact: {output}")
    print(f"Arquivos: {len(manifest_entries)}")
    print(f"Source commit: {build_info['sourceCommit']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="_site")
    args = parser.parse_args()
    build(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

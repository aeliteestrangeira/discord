from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "0082-d8680b1c1576ecc8.svg": "https://res.cloudinary.com/do7vwsnpg/image/upload/v1787132568/0082-d8680b1c1576ecc8_rrwlpk.svg",
    "0083-131c318dd45b7aa4.svg": "https://res.cloudinary.com/do7vwsnpg/image/upload/v1787132620/0083-131c318dd45b7aa4_i9zgvc.svg",
    "login-qr-icon.png": "https://res.cloudinary.com/do7vwsnpg/image/upload/v1787132650/login-qr-icon_flnowo.png",
}


class CloudinaryLoginVisualAssetTests(unittest.TestCase):
    def test_login_visual_assets_are_pinned_to_supplied_cloudinary_urls(self):
        login = (ROOT / "priv" / "static" / "pages" / "login.html").read_text(encoding="utf-8")
        assets = (ROOT / "lib" / "discord_app_web" / "controllers" / "assets.py").read_text(encoding="utf-8")
        for filename, url in EXPECTED.items():
            self.assertIn(f"images/{filename}", login)
            self.assertIn(f'"{filename}": "{url}"', assets)
        self.assertIn("PINNED_CLOUDINARY_IMAGE_URLS.get(canonical)", assets)
        self.assertIn("return redirect(external_url, code=302)", assets)

    def test_pinned_cloudinary_map_is_closed_to_exact_login_assets(self):
        assets = (ROOT / "lib" / "discord_app_web" / "controllers" / "assets.py").read_text(encoding="utf-8")
        for filename in EXPECTED:
            self.assertEqual(assets.count(f'"{filename}":'), 1)
        self.assertEqual(assets.count("https://res.cloudinary.com/do7vwsnpg/image/upload/v"), 3)


if __name__ == "__main__":
    unittest.main()

"use strict";

const download = document.querySelector("#download");
const status = document.querySelector("#release-status");

async function resolveLatestRelease() {
  try {
    const response = await fetch("https://api.github.com/repos/aeliteestrangeira/discord/releases/latest", {
      headers: { Accept: "application/vnd.github+json" },
      cache: "no-store"
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const release = await response.json();
    const assets = Array.isArray(release.assets) ? release.assets : [];
    const installer = assets.find((asset) => /^Discord-Desktop-Setup-.*-x64\.exe$/i.test(asset.name || ""));
    if (installer?.browser_download_url) download.href = installer.browser_download_url;
    const version = release.tag_name || release.name || "versão atual";
    status.textContent = installer ? `${version} · instalador x64 disponível` : `${version} · veja os arquivos da release`;
  } catch (_) {
    status.textContent = "Abra Releases para consultar a versão mais recente.";
  }
}

void resolveLatestRelease();

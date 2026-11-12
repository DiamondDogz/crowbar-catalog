"""Composants facultatifs de Crowbar, installés seulement si l'utilisateur les demande.

Pour l'instant : le lecteur vidéo de « Mes vidéos » (mpv pour Windows, compilé par shinchiro).
Le script trouve la dernière version publiée, télécharge l'archive, calcule son empreinte SHA-256
et écrit components.json. Crowbar télécharge ensuite l'archive directement à la source et vérifie
l'empreinte : il ne redistribue pas lui-même le lecteur.
"""
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.request

SOURCE = "shinchiro/mpv-winbuild-cmake"
# L'archive x86_64 générique (pas la v3, réservée aux processeurs récents, ni les paquets de dev).
ASSET = re.compile(r"^mpv-x86_64-\d{8}-git-[0-9a-f]+\.7z$")


def api(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "crowbar-catalog"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def pick(assets):
    """L'archive à proposer parmi les fichiers d'une version, ou None."""
    for a in assets:
        if ASSET.match(a.get("name", "")):
            return a
    return None


def sha256_of(url):
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "crowbar-catalog"})
    size = 0
    with urllib.request.urlopen(req, timeout=600) as r:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def main(path="components.json"):
    old = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    rel = api(f"https://api.github.com/repos/{SOURCE}/releases/latest")
    asset = pick(rel.get("assets", []))
    if not asset:
        print("aucune archive reconnue dans la dernière version", file=sys.stderr)
        return 1
    url = asset["browser_download_url"]
    prev = old.get("video", {}).get("windows", {})
    if prev.get("url") == url and prev.get("sha256"):
        print("Rien de nouveau :", asset["name"])
        return 0
    digest, size = sha256_of(url)
    out = {
        "schemaVersion": 1,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "video": {
            "windows": {
                "version": rel.get("tag_name", ""),
                "file": asset["name"],
                "url": url,
                "size": size,
                "sha256": digest,
                "exe": "mpv.exe",
                "source": f"https://github.com/{SOURCE}",
                "license": "GPL-2.0-or-later",
            }
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("components.json :", asset["name"], digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())

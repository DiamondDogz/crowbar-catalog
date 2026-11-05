#!/usr/bin/env python3
"""Génère releases.json à partir de catalog.json et des releases GitHub de chaque runtime.

Pour chaque runtime du catalogue, on retient :
- « stable » : la release publiée la plus récente qui n'est pas une préversion ;
- « beta »   : la release publiée la plus récente, préversions comprises.

Crowbar ne lit que releases.json : les joueurs n'appellent jamais l'API GitHub.
Usage : python scripts/build_releases.py [--offline fichier-de-test.json]
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
NOTES_MAX = 4000  # notes de version tronquées, pour garder releases.json léger
VERSIONS_MAX = 10  # versions proposées dans Crowbar pour revenir en arrière ou en choisir une
VERSION_NOTES_MAX = 600


def http_get(url: str, accept: str = "application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "crowbar-catalog"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith(API):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def fetch_releases(repo: str) -> list[dict]:
    return json.loads(http_get(f"{API}/repos/{repo}/releases?per_page=50"))


def fetch_repo(repo: str) -> dict:
    return json.loads(http_get(f"{API}/repos/{repo}"))


def parse_sha256(text: str, asset_name: str) -> str | None:
    """Lit un fichier .sha256 (« empreinte  nom » ou empreinte seule)."""
    for line in text.splitlines():
        parts = line.strip().split()
        if not parts or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            continue
        if len(parts) == 1 or parts[-1].lstrip("*").endswith(asset_name):
            return parts[0].lower()
    return None


def pick_asset(release: dict, spec: dict) -> dict | None:
    for asset in release.get("assets", []):
        if fnmatch.fnmatch(asset["name"], spec["asset"]):
            return asset
    return None


def describe(release: dict, spec: dict, read=http_get) -> dict | None:
    """Résume une release pour Crowbar, ou None si elle n'a pas l'archive attendue."""
    asset = pick_asset(release, spec)
    if not asset:
        return None
    sha = None
    if spec.get("checksum"):
        name = spec["checksum"].replace("{asset}", asset["name"])
        side = next((a for a in release.get("assets", []) if a["name"] == name), None)
        if side:
            try:
                sha = parse_sha256(read(side["browser_download_url"], "application/octet-stream").decode("utf-8", "replace"), asset["name"])
            except (urllib.error.URLError, OSError):
                sha = None
    if not sha and str(asset.get("digest", "")).startswith("sha256:"):
        sha = asset["digest"].split(":", 1)[1].lower()
    tag = release["tag_name"]
    prefix = spec.get("tagPrefix", "")
    return {
        "version": tag[len(prefix):] if prefix and tag.startswith(prefix) else tag,
        "tag": tag,
        "prerelease": bool(release.get("prerelease")),
        "published": release.get("published_at"),
        "url": asset["browser_download_url"],
        "file": asset["name"],
        "size": asset.get("size", 0),
        "sha256": sha,
        "notes": (release.get("body") or "")[:NOTES_MAX],
        "page": release.get("html_url"),
    }


def resolve(releases: list[dict], spec: dict, read=http_get) -> dict:
    """Choisit les releases « stable » et « beta » d'un runtime, et liste les dernières versions."""
    prefix = spec.get("tagPrefix", "")
    usable = [r for r in releases
              if not r.get("draft") and r.get("published_at") and r["tag_name"].startswith(prefix)]
    usable.sort(key=lambda r: r["published_at"], reverse=True)
    out: dict = {}
    for r in usable:
        if "beta" not in out:
            d = describe(r, spec, read)
            if d:
                out["beta"] = d
        if "stable" not in out and not r.get("prerelease"):
            d = describe(r, spec, read)
            if d:
                out["stable"] = d
        if "beta" in out and "stable" in out:
            break
    # Les dernières versions publiées, pour en choisir une précise dans Crowbar.
    versions = []
    for r in usable:
        if len(versions) >= VERSIONS_MAX:
            break
        d = out["beta"] if out.get("beta", {}).get("tag") == r["tag_name"] else \
            out["stable"] if out.get("stable", {}).get("tag") == r["tag_name"] else describe(r, spec, read)
        if d:
            versions.append({**d, "notes": d["notes"][:VERSION_NOTES_MAX]})
    if versions:
        out["versions"] = versions
    return out


def build(catalog: dict, fetch=fetch_releases, read=http_get, info=fetch_repo) -> tuple[dict, list[str]]:
    result = {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "games": {}}
    problems: list[str] = []
    for game in catalog["games"]:
        entry = {}
        for spec in game.get("runtimes", []):
            key = spec["platform"]
            try:
                releases = fetch(spec["repo"])
            except (urllib.error.URLError, OSError, ValueError) as e:
                problems.append(f"{game['id']}/{key} : {spec['repo']} illisible ({e})")
                continue
            channels = resolve(releases, spec, read)
            if not channels:
                names = sorted({a["name"] for r in releases for a in r.get("assets", [])})[:12]
                problems.append(f"{game['id']}/{key} : aucune archive « {spec['asset']} » dans {spec['repo']} (fichiers vus : {', '.join(names) or 'aucun'})")
                continue
            try:
                stars = int(info(spec["repo"]).get("stargazers_count", 0))
            except (urllib.error.URLError, OSError, ValueError):
                stars = None
            entry[key] = {"repo": spec["repo"], "maintainer": spec.get("maintainer", ""), "stars": stars,
                          "launch": spec.get("launch", "ps4rt-launch"), **channels}
        result["games"][game["id"]] = entry
    return result, problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", type=Path, help="releases simulées {dépôt: [releases]} pour tester")
    args = parser.parse_args()
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    fetch = fetch_releases
    if args.offline:
        fake = json.loads(args.offline.read_text(encoding="utf-8"))
        fetch = lambda repo: fake.get(repo, [])
        result, problems = build(catalog, fetch, info=lambda repo: {})
    else:
        result, problems = build(catalog, fetch)
    old = ROOT / "releases.json"
    if old.exists():
        previous = json.loads(old.read_text(encoding="utf-8"))
        if previous.get("games") == result["games"]:
            print("releases.json inchangé")
            for p in problems:
                print("ATTENTION :", p)
            return 0
    old.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("releases.json mis à jour")
    for p in problems:
        print("ATTENTION :", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())

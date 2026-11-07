#!/usr/bin/env python3
"""Turns an « Add a runtime » issue into a catalog change, after checking the release.

Run by .github/workflows/add-runtime.yml. The issue body is untrusted text: it is only parsed
as data, never executed or passed to a shell. Nothing is merged here: the workflow opens a pull
request that a maintainer reviews.

    python scripts/add_runtime.py --body issue.md --report report.md [--sdk path/to/crowbar-sdk]
Exit code 0 when catalog.json was changed and every check passed, 1 otherwise.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
MAX_DOWNLOAD = 3 * 1024 ** 3  # 3 Go
FIELDS = {
    "Game": "game", "Game name": "name", "CUSA ids": "titleIds", "GitHub repository": "repo",
    "Release file": "asset", "System": "platform", "Checksum file": "checksum",
    "Tag prefix": "tagPrefix", "Maintainer": "maintainer",
}


# ---------- the form ----------

def parse_form(body: str) -> dict:
    """GitHub issue forms render as « ### Label » followed by the answer."""
    out: dict[str, str] = {}
    parts = re.split(r"^###\s+(.+?)\s*$", body.replace("\r\n", "\n"), flags=re.M)
    for label, value in zip(parts[1::2], parts[2::2]):
        key = FIELDS.get(label.strip())
        if not key:
            continue
        v = value.strip()
        if v in ("_No response_", "None"):
            v = ""
        out[key] = v
    return out


def validate_form(f: dict) -> list[str]:
    errs = []
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}", f.get("repo", "")):
        errs.append("« GitHub repository » doit être de la forme `owner/repo`.")
    if f.get("platform") not in ("windows", "linux"):
        errs.append("« System » doit être `windows` ou `linux`.")
    asset = f.get("asset", "")
    if not asset or "/" in asset or "\\" in asset or len(asset) > 200 or not re.fullmatch(r"[A-Za-z0-9._*+-]+", asset):
        errs.append("« Release file » doit être un nom de fichier, `*` pour la partie qui change (lettres, chiffres, `. _ - + *`).")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", f.get("game", "")):
        errs.append("« Game » doit être l'identifiant du jeu dans le catalogue (minuscules et tirets).")
    if f.get("checksum") and not re.fullmatch(r"[A-Za-z0-9._{}*+-]+", f["checksum"]):
        errs.append("« Checksum file » doit être un nom de fichier, par exemple `{asset}.sha256`.")
    if f.get("tagPrefix") and not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", f["tagPrefix"]):
        errs.append("« Tag prefix » ne peut contenir que lettres, chiffres et `. _ -`.")
    if f.get("titleIds"):
        ids = [t for t in re.split(r"[\s,]+", f["titleIds"]) if t]
        if not ids or not all(re.fullmatch(r"(CUSA|PLJS|PLJM|PCJS|PCAS|PLAS)\d{5}", t) for t in ids):
            errs.append("« CUSA ids » : des identifiants comme `CUSA16429`, séparés par des virgules.")
    return errs


# ---------- GitHub ----------

def http_get(url: str, accept: str = "application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "crowbar-catalog"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith(API):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def latest_release(repo: str, tag_prefix: str, asset_glob: str, releases=None) -> tuple[dict, dict]:
    """The newest published release (pre-releases included) that has a matching file."""
    releases = releases if releases is not None else json.loads(http_get(f"{API}/repos/{repo}/releases?per_page=30"))
    for rel in releases:
        if rel.get("draft") or (tag_prefix and not rel.get("tag_name", "").startswith(tag_prefix)):
            continue
        for a in rel.get("assets", []):
            if fnmatch.fnmatch(a["name"], asset_glob):
                return rel, a
    raise LookupError(f"aucune release de {repo} ne contient de fichier « {asset_glob} »")


def download(url: str, dest: Path, size: int) -> str:
    if size > MAX_DOWNLOAD:
        raise ValueError(f"fichier trop gros ({size // 1024 ** 2} Mo)")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"Accept": "application/octet-stream", "User-Agent": "crowbar-catalog"})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as out:
        total = 0
        while chunk := r.read(1 << 20):
            total += len(chunk)
            if total > MAX_DOWNLOAD:
                raise ValueError("fichier trop gros")
            h.update(chunk)
            out.write(chunk)
    return h.hexdigest()


def parse_sha256(text: str, name: str) -> str | None:
    for line in text.splitlines():
        parts = line.strip().split()
        if parts and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]) and (len(parts) == 1 or parts[-1].lstrip("*") == name):
            return parts[0].lower()
    return None


# ---------- catalog.json, written in its own style ----------

def dumps(v, indent=0, inline=False) -> str:
    """Like the hand-written file: objects one key per line, lists of plain values on one line,
    and each runtime entry on a single line (a change to a runtime is a one-line diff)."""
    pad, inner = "  " * indent, "  " * (indent + 1)
    if isinstance(v, dict):
        if not v:
            return "{}"
        if inline:
            return "{" + ", ".join(f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(x, ensure_ascii=False)}" for k, x in v.items()) + "}"
        return "{\n" + ",\n".join(f"{inner}{json.dumps(k, ensure_ascii=False)}: {dumps(x, indent + 1, k == 'runtimes')}" for k, x in v.items()) + f"\n{pad}}}"
    if isinstance(v, list):
        if not v:
            return "[]"
        if all(not isinstance(x, (dict, list)) for x in v):
            return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in v) + "]"
        flat = lambda x: isinstance(x, dict) and all(not isinstance(y, (dict, list)) for y in x.values())
        return "[\n" + ",\n".join(f"{inner}{dumps(x, indent + 1, inline and flat(x))}" for x in v) + f"\n{pad}]"
    return json.dumps(v, ensure_ascii=False)


def apply(catalog: dict, f: dict, sha_note: str) -> tuple[dict, str]:
    """Adds or replaces the runtime entry. Returns (entry, what happened)."""
    entry = {"platform": f["platform"], "repo": f["repo"]}
    if f.get("tagPrefix"):
        entry["tagPrefix"] = f["tagPrefix"]
    entry["asset"] = f["asset"]
    if f.get("checksum"):
        entry["checksum"] = f["checksum"]
    entry["maintainer"] = f.get("maintainer") or f["repo"].split("/")[0]
    entry["launch"] = "crowbar-json"
    entry["trophies"] = bool(f.get("_trophies"))
    games = catalog.setdefault("games", [])
    game = next((g for g in games if g.get("id") == f["game"]), None)
    if game is None:
        if not f.get("name") or not f.get("titleIds"):
            raise ValueError(f"le jeu « {f['game']} » n'est pas dans le catalogue : remplissez aussi « Game name » et « CUSA ids »")
        ids = [t for t in re.split(r"[\s,]+", f["titleIds"]) if t]
        game = {"id": f["game"], "name": f["name"], "titleIds": ids,
                "match": re.sub(r"[^a-z0-9]+", r"\\s*", f["name"].lower()).strip("\\s*") or f["game"],
                "genre": "", "runtimes": []}
        games.append(game)
        what = f"nouveau jeu « {f['name']} »"
    else:
        what = f"jeu existant « {game.get('name')} »"
    rts = game.setdefault("runtimes", [])
    same = [i for i, r in enumerate(rts) if r.get("platform") == entry["platform"] and r.get("repo", "").lower() == entry["repo"].lower()]
    if same:
        rts[same[0]] = entry
        what += ", runtime remplacé"
    else:
        rts.append(entry)
        what += ", runtime ajouté"
    return entry, what


# ---------- main ----------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True, help="file with the issue body")
    ap.add_argument("--report", required=True, help="Markdown report to write")
    ap.add_argument("--sdk", default=str(ROOT / "sdk"), help="crowbar-sdk checkout (for crowbar-check)")
    a = ap.parse_args(argv)
    lines = ["## Vérification automatique", ""]
    ok = False
    try:
        form = parse_form(Path(a.body).read_text(encoding="utf-8"))
        errs = validate_form(form)
        if errs:
            raise ValueError("\n".join(f"- {e}" for e in errs))
        rel, asset = latest_release(form["repo"], form.get("tagPrefix", ""), form["asset"])
        lines.append(f"- Release **{rel['tag_name']}** · `{asset['name']}` · {asset['size'] / 1024 ** 2:.1f} Mo")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / asset["name"]
            sha = download(asset["browser_download_url"], path, asset["size"])
            expected, source = None, ""
            if form.get("checksum"):
                side_name = form["checksum"].replace("{asset}", asset["name"])
                side = next((x for x in rel.get("assets", []) if x["name"] == side_name), None)
                if side is None:
                    raise ValueError(f"fichier d'empreinte « {side_name} » absent de la release")
                expected = parse_sha256(http_get(side["browser_download_url"], "application/octet-stream").decode("utf-8", "replace"), asset["name"])
                source = side_name
            elif str(asset.get("digest", "")).startswith("sha256:"):
                expected, source = asset["digest"].split(":", 1)[1].lower(), "empreinte GitHub"
            if expected and expected != sha:
                raise ValueError(f"SHA-256 différent de {source} : {sha} au lieu de {expected}")
            lines.append(f"- ✓ SHA-256 `{sha[:12]}…`" + (f" identique à {source}" if expected else " (aucune empreinte publiée pour comparer)"))
            sys.path.insert(0, a.sdk)
            from crowbar_sdk import check  # noqa: E402  (crowbar-sdk, checked out by the workflow)
            r = check.run(path)
        for e in r["errors"]:
            lines.append(f"- ✗ `{e['code']}` {e['message']}" + (f" → {e['fix']}" if e.get("fix") else ""))
        for w in r["warnings"]:
            lines.append(f"- ! `{w['code']}` {w['message']}")
        if not r["manifest"]:
            raise ValueError("la release n'a pas de `crowbar.json` à sa racine")
        if r["errors"]:
            raise ValueError("crowbar-check signale des erreurs dans la release (ci-dessus)")
        lines.append("- ✓ `crowbar.json` présent et valide, aucun fichier de jeu ni clé détecté")
        form["_trophies"] = bool(((r.get("manifestData") or {}).get("features") or {}).get("trophies"))
        catalog_path = ROOT / "catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        entry, what = apply(catalog, form, sha)
        catalog_path.write_text(dumps(catalog) + "\n", encoding="utf-8")
        lines += ["", f"**{what}.** Entrée proposée :", "", "```json", dumps(entry), "```", "",
                  "Une demande d'ajout est ouverte : elle sera relue avant d'arriver dans Crowbar."]
        ok = True
    except Exception as e:  # every problem goes into the issue comment, in plain words
        lines += ["", "**Ajout impossible pour l'instant :**", "", str(e), "",
                  "Corrigez la release ou le formulaire (modifier le ticket relance la vérification)."]
    Path(a.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

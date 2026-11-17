"""GitHub deposunu okur ve proje özetini data/projeler altına yazar."""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from langchain_core.tools import tool

from config import get_settings
from tools.common import COMPANY
from tools.json_store import save_json_safe

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT / "data" / "projeler"

DEPENDENCY_NAMES = (
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "pyproject.toml",
    "Pipfile",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "composer.json",
    "Gemfile",
)
SKIP_PARTS = ("node_modules/", ".git/", "dist/", "build/", "__pycache__/", ".venv/", "vendor/")
README_LIMIT = 8000
FILE_LIMIT = 4000
TREE_LIMIT = 300


class GithubError(RuntimeError):
    """GitHub API'nin döndürdüğü, kullanıcıya gösterilebilir hata."""


def parse_repo_url(repo_url: str) -> tuple[str, str] | None:
    text = (repo_url or "").strip().rstrip("/")
    text = re.sub(r"\.git$", "", text, flags=re.IGNORECASE)
    hosted = re.search(r"github\.com[:/](?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)", text, re.IGNORECASE)
    if hosted:
        return hosted.group("owner"), hosted.group("repo")
    plain = re.fullmatch(r"([\w.-]+)/([\w.-]+)", text)
    if plain:
        return plain.group(1), plain.group(2)
    return None


def slug_for(owner: str, repo: str) -> str:
    return f"{owner}__{repo}"


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bcd-technologies-multiagent",
    }
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url: str, *, required: bool = True) -> dict | list | None:
    try:
        response = httpx.get(url, headers=github_headers(), timeout=20.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise GithubError(f"GitHub'a ulaşılamadı ({exc.__class__.__name__}).") from exc
    if response.status_code in {401, 403}:
        raise GithubError("GitHub isteği reddedildi. GITHUB_TOKEN değerini kontrol edin.")
    if response.status_code == 404:
        if not required:
            return None
        if get_settings().github_token:
            raise GithubError("Depo bulunamadı.")
        raise GithubError("Depo bulunamadı veya gizli. .env içine GITHUB_TOKEN ekleyin.")
    if response.status_code >= 400:
        if not required:
            return None
        raise GithubError(f"GitHub HTTP {response.status_code} döndürdü.")
    payload = response.json()
    if not isinstance(payload, (dict, list)):
        raise GithubError("GitHub beklenmeyen bir yanıt döndürdü.")
    return payload


def _decode_readme(payload: dict) -> str:
    content = str(payload.get("content") or "")
    if not content:
        return ""
    try:
        text = base64.b64decode(content).decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        return ""
    text = text.strip()
    if len(text) > README_LIMIT:
        return text[:README_LIMIT] + "\n…"
    return text


def _keep_path(path: str) -> bool:
    lowered = path.lower()
    return not any(part in lowered for part in SKIP_PARTS)


def download_repo(owner: str, repo: str) -> dict:
    meta = _get_json(f"https://api.github.com/repos/{owner}/{repo}")
    if not isinstance(meta, dict):
        raise GithubError("Depo bilgisi okunamadı.")
    branch = str(meta.get("default_branch") or "HEAD")
    readme_payload = _get_json(f"https://api.github.com/repos/{owner}/{repo}/readme", required=False)
    readme = _decode_readme(readme_payload) if isinstance(readme_payload, dict) else ""
    tree_payload = _get_json(
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1",
        required=False,
    )
    paths: list[str] = []
    if isinstance(tree_payload, dict):
        for item in tree_payload.get("tree") or []:
            if not isinstance(item, dict) or item.get("type") != "blob":
                continue
            path = str(item.get("path") or "")
            if path and _keep_path(path):
                paths.append(path)
    paths = paths[:TREE_LIMIT]
    dependencies: dict[str, str] = {}
    available = set(paths)
    for name in DEPENDENCY_NAMES:
        matches = [path for path in available if path == name or path.endswith("/" + name)]
        for path in matches[:3]:
            file_payload = _get_json(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}",
                required=False,
            )
            if isinstance(file_payload, dict) and file_payload.get("encoding") == "base64":
                try:
                    text = base64.b64decode(str(file_payload.get("content") or "")).decode(
                        "utf-8", errors="replace"
                    )
                except (ValueError, UnicodeError):
                    text = ""
                dependencies[path] = text.strip()[:FILE_LIMIT]
    languages_payload = _get_json(
        f"https://api.github.com/repos/{owner}/{repo}/languages",
        required=False,
    )
    languages = list(languages_payload) if isinstance(languages_payload, dict) else []
    return {
        "company": COMPANY,
        "owner": owner,
        "repo": repo,
        "slug": slug_for(owner, repo),
        "url": f"https://github.com/{owner}/{repo}",
        "description": str(meta.get("description") or "").strip(),
        "default_branch": branch,
        "private": bool(meta.get("private")),
        "language": str(meta.get("language") or ""),
        "languages": languages,
        "readme": readme,
        "tree": paths,
        "dependencies": dependencies,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def save_project(record: dict) -> Path:
    path = PROJECTS_DIR / f"{record['slug']}.json"
    save_json_safe(path, record)
    return path


def list_projects() -> list[Path]:
    if not PROJECTS_DIR.exists():
        return []
    return sorted(PROJECTS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime)


def load_project(query: str = "") -> dict | None:
    files = list_projects()
    if not files:
        return None
    needle = (query or "").strip().lower().replace("\\", "/")
    parsed = parse_repo_url(needle)
    if parsed:
        needle = slug_for(*parsed).lower()
    if needle:
        for path in files:
            if needle in path.stem.lower() or needle in path.read_text(encoding="utf-8").lower():
                return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(files[-1].read_text(encoding="utf-8"))


def format_project(record: dict) -> str:
    tree = record.get("tree") or []
    preview = "\n".join(f"- {path}" for path in tree[:40]) or "- (dosya yok)"
    deps = record.get("dependencies") or {}
    dep_lines = []
    for name, content in deps.items():
        snippet = "\n".join(str(content).splitlines()[:20])
        dep_lines.append(f"### {name}\n{snippet}")
    languages = ", ".join(record.get("languages") or []) or record.get("language") or "belirtilmedi"
    readme = str(record.get("readme") or "").strip() or "(README yok)"
    return "\n".join(
        [
            f"{COMPANY} proje kaydı",
            f"slug: {record.get('slug')}",
            f"Depo: {record.get('url')}",
            f"Açıklama: {record.get('description') or 'yok'}",
            f"Dal: {record.get('default_branch')} | Dil: {languages}",
            "",
            "README:",
            readme,
            "",
            f"Dosya ağacı ({len(tree)} dosya):",
            preview,
            "",
            "Bağımlılıklar:",
            "\n\n".join(dep_lines) or "(bağımlılık dosyası yok)",
        ]
    )


@tool
def fetch_github_repo(repo_url: str) -> str:
    """GitHub deposunun README.md dosyasını, dosya ağacını ve bağımlılık dosyalarını indirir.

    repo_url tam adres veya owner/repo olabilir. Gizli depolar .env içindeki GITHUB_TOKEN ile okunur.
    Özet data/projeler altına yazılır.
    """
    parsed = parse_repo_url(repo_url)
    if parsed is None:
        return "Hata: Geçerli bir GitHub adresi verin. Örnek: https://github.com/bariscandasci/ankaras"
    owner, repo = parsed
    try:
        record = download_repo(owner, repo)
    except GithubError as exc:
        return f"Hata: {exc}"
    path = save_project(record)
    return format_project(record) + f"\n\nDosya: {path.as_posix()}"


@tool
def read_project(query: str = "") -> str:
    """Kaydedilmiş proje özetini okur. query boşsa son depo gelir; owner/repo de kabul edilir."""
    record = load_project(query)
    if record is None:
        return "Kayıtlı proje yok. Önce bir GitHub adresi verin."
    return format_project(record)


GITHUB_TOOLS = [fetch_github_repo, read_project]

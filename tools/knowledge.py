"""Kurumsal dokümanları parçalar ve ajana sorguyla en yakın parçaları seçer."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from tools.common import fold
from tools.json_store import json_lock, save_json_safe

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "data" / "bilgi_bankasi" / "index.json"

DEPARTMENTS = ("all", "manager", "market", "rnd", "finance")
AGENT_DEPARTMENT = {
    "supervisor": "manager",
    "market": "market",
    "rnd": "rnd",
    "finance": "finance",
}
DEPARTMENT_LABELS = {
    "all": "Tüm Şirket",
    "manager": "Yönetici",
    "market": "Operasyon & Pazar",
    "rnd": "Teknik & Ar-Ge",
    "finance": "Muhasebe & Finans",
}
ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
MAX_CHUNKS = 80
TOP_K = 4
MAX_REFERENCE_CHARS = 3500
SUMMARY_CHARS = 320

_TOKEN = re.compile(r"[a-z0-9]{2,}")


class KnowledgeError(ValueError):
    """Yüklenen dosya okunamadı veya kabul edilmedi."""


def _read_index() -> dict:
    path = INDEX_PATH
    if not path.is_file():
        return {"documents": []}
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"documents": []}
    documents = [item for item in payload.get("documents") or [] if isinstance(item, dict)]
    return {"documents": documents}


def _write_index(payload: dict) -> None:
    save_json_safe(INDEX_PATH, payload)


def _next_id(documents: list[dict]) -> str:
    best = 0
    for item in documents:
        raw = str(item.get("id") or "")
        if raw.startswith("kb-") and raw[3:].isdigit():
            best = max(best, int(raw[3:]))
    return f"kb-{best + 1}"


def _title_from(filename: str) -> str:
    stem = Path(filename).stem.strip() or "dokuman"
    cleaned = re.sub(r"\s+", " ", stem)
    return cleaned[:120]


def _extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def extract_text(filename: str, payload: bytes) -> str:
    if len(payload) > MAX_UPLOAD_BYTES:
        raise KnowledgeError("Dosya 8 MB sınırını aşıyor.")
    if not payload:
        raise KnowledgeError("Dosya boş.")
    extension = _extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise KnowledgeError("Yalnız .md, .txt ve .pdf dosyaları kabul edilir.")
    if extension == ".pdf":
        text = _pdf_text(payload)
    else:
        text = payload.decode("utf-8-sig", errors="replace")
    text = text.replace("\x00", " ").strip()
    if not text:
        raise KnowledgeError("Dokümandan metin okunamadı.")
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
    return text


def _pdf_text(payload: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise KnowledgeError("PDF okuyucu kurulu değil.") from exc
    try:
        reader = PdfReader(BytesIO(payload))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise KnowledgeError("PDF okunamadı.") from exc
    return "\n".join(pages)


def chunk_text(text: str) -> list[str]:
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not cleaned:
        return []
    if len(cleaned) <= CHUNK_SIZE:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned) and len(chunks) < MAX_CHUNKS:
        end = min(len(cleaned), start + CHUNK_SIZE)
        if end < len(cleaned):
            break_at = cleaned.rfind("\n", start + CHUNK_SIZE // 2, end)
            if break_at == -1:
                break_at = cleaned.rfind(" ", start + CHUNK_SIZE // 2, end)
            if break_at > start:
                end = break_at
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(cleaned):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def _summary(text: str) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= SUMMARY_CHARS:
        return flat
    return flat[: SUMMARY_CHARS - 1].rstrip() + "…"


def _public(document: dict) -> dict:
    return {
        "id": document["id"],
        "title": document["title"],
        "filename": document.get("filename") or document["title"],
        "department": document["department"],
        "summary": document.get("summary") or "",
        "chunk_count": len(document.get("chunks") or []),
        "created_at": document.get("created_at") or "",
    }


def list_documents() -> list[dict]:
    return [_public(item) for item in _read_index()["documents"]]


def add_document(filename: str, department: str, payload: bytes) -> dict:
    target = department.strip().lower()
    if target not in DEPARTMENTS:
        raise KnowledgeError("Departman geçersiz.")
    safe_name = Path(filename or "dokuman.txt").name
    text = extract_text(safe_name, payload)
    chunks = chunk_text(text)
    if not chunks:
        raise KnowledgeError("Dokümandan metin okunamadı.")
    with json_lock(INDEX_PATH):
        index = _read_index()
        document = {
            "id": _next_id(index["documents"]),
            "title": _title_from(safe_name),
            "filename": safe_name,
            "department": target,
            "summary": _summary(text),
            "chunks": chunks,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        index["documents"].append(document)
        _write_index(index)
    return _public(document)


def delete_document(doc_id: str) -> bool:
    with json_lock(INDEX_PATH):
        index = _read_index()
        kept = [item for item in index["documents"] if item.get("id") != doc_id]
        if len(kept) == len(index["documents"]):
            return False
        index["documents"] = kept
        _write_index(index)
    return True


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(fold(text))


def search_chunks(agent_id: str, query: str, limit: int = TOP_K) -> list[dict]:
    department = AGENT_DEPARTMENT.get(agent_id, "")
    if not department or not query.strip():
        return []
    rows: list[tuple[dict, str, list[str]]] = []
    for document in _read_index()["documents"]:
        scope = str(document.get("department") or "")
        if scope not in {department, "all"}:
            continue
        for chunk in document.get("chunks") or []:
            if isinstance(chunk, str) and chunk.strip():
                rows.append((document, chunk, _tokens(chunk)))
    if not rows:
        return []
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    document_frequency: dict[str, int] = {}
    for _, _, tokens in rows:
        for token in set(tokens):
            document_frequency[token] = document_frequency.get(token, 0) + 1
    total = len(rows)
    ranked: list[tuple[float, dict, str]] = []
    for document, chunk, tokens in rows:
        if not tokens:
            continue
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        score = 0.0
        for token in query_tokens:
            seen = counts.get(token)
            if not seen:
                continue
            idf = math.log((total + 1) / (document_frequency.get(token, 0) + 1)) + 1
            score += (seen / len(tokens)) * idf
        if score > 0:
            ranked.append((score, document, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    picked: list[dict] = []
    seen_chunks: set[str] = set()
    for _, document, chunk in ranked:
        if chunk in seen_chunks:
            continue
        seen_chunks.add(chunk)
        picked.append(
            {
                "title": document.get("title") or "Doküman",
                "department": document.get("department") or "all",
                "text": chunk,
            }
        )
        if len(picked) >= limit:
            break
    return picked


def reference_block(agent_id: str, query: str) -> str:
    matches = search_chunks(agent_id, query)
    if not matches:
        return ""
    lines = [
        "KURUMSAL REFERANS DOKÜMANLARI",
        "Bu dokümanlardaki şablonlar, fiyatlandırma kuralları ve teknik standartlar önceliklidir. "
        "Dokümanda olmayan fiyat, müşteri veya standart uydurma.",
    ]
    used = len("\n".join(lines))
    for match in matches:
        label = DEPARTMENT_LABELS.get(match["department"], match["department"])
        block = f"Kaynak: {match['title']} ({label})\n{match['text']}"
        if used + len(block) > MAX_REFERENCE_CHARS:
            remaining = MAX_REFERENCE_CHARS - used
            if remaining < 80:
                break
            block = block[:remaining].rstrip()
        lines.append(block)
        used += len(block)
    return "\n\n".join(lines)

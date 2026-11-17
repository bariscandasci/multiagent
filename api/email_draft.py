"""Seçili proje analizi için B2B tanıtım ve demo talep e-postası."""

from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from agents.context import agent_temperature, compose_prompt
from agents.runtime import message_text
from config import bind_agent_model, describe_llm_error, get_settings
from tools.common import COMPANY

logger = logging.getLogger(__name__)

EMAIL_DIRECTIVE = f"""Sen {COMPANY} satış yazarısın.
Sana verilen proje analizi ve hedef müşteri profilinden profesyonel bir B2B tanıtım e-postası yaz.
Yalnızca JSON döndür: {{"subject":"...","body":"..."}}
Konu 90 karakteri geçmesin. Gövde Türkçe, kurumsal ve kısa olsun.
Demo talep et. Raporda olmayan fiyat, müşteri adı veya metrik uydurma.
İmza satırı: {COMPANY}"""


def draft_sales_email(project_name: str, customer_profile: str, sections: dict) -> dict:
    settings = get_settings()
    if settings.configured:
        try:
            subject, body = _from_model(project_name, customer_profile, sections)
        except Exception as exc:
            logger.warning("E-posta taslağı kural metnine düştü: %s", describe_llm_error(exc))
        else:
            return {
                "subject": subject,
                "body": body,
                "mode": "llm",
                "model": settings.model,
            }
    drafted = _template(project_name, customer_profile, sections)
    drafted["model"] = ""
    return drafted


def _from_model(project_name: str, customer_profile: str, sections: dict) -> tuple[str, str]:
    model = bind_agent_model(get_settings(), agent_temperature("market"))
    system = compose_prompt("market", EMAIL_DIRECTIVE)
    brief = "\n\n".join(
        part
        for part in (
            f"Proje: {project_name or 'belirtilmedi'}",
            f"Hedef müşteri profili: {customer_profile}",
            f"Yönetici özeti:\n{_excerpt(sections.get('executive') or '', 1200)}",
            f"Pazar analizi:\n{_excerpt(sections.get('market') or '', 1800)}",
            f"Finans notu:\n{_excerpt(sections.get('finance') or '', 800)}",
        )
        if part.strip()
    )
    message = model.invoke([SystemMessage(content=system), HumanMessage(content=brief)])
    return _parse_draft(message_text(message.content))


def _parse_draft(text: str) -> tuple[str, str]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("model JSON döndürmedi")
    payload = json.loads(match.group(0))
    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not subject or not body:
        raise ValueError("model konu veya gövde döndürmedi")
    return subject[:120], body


def _template(project_name: str, customer_profile: str, sections: dict) -> dict:
    project = project_name.strip() or "ilgili çalışma"
    analysis = _excerpt(sections.get("market") or sections.get("executive") or "Kayıtlı proje analizi paylaşılabilir.")
    subject = f"{project} için tanıtım ve demo talebi"
    if len(subject) > 90:
        subject = subject[:87].rstrip() + "..."
    body = "\n".join(
        [
            "Merhaba,",
            "",
            f"{customer_profile.strip()} profiline uygun bir tanıtım hazırladık.",
            f"{COMPANY} olarak {project} çalışmasını kısaca paylaşmak isteriz.",
            "",
            analysis,
            "",
            "Ürünü kendi akışınızda görmeniz için kısa bir demo planlayabiliriz. Uygun olduğunuz bir zamanı paylaşır mısınız?",
            "",
            "Saygılarımızla,",
            COMPANY,
        ]
    )
    return {"subject": subject, "body": body, "mode": "mock"}


def _excerpt(text: str, limit: int = 700) -> str:
    cleaned = re.sub(r"[#*`]", "", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"

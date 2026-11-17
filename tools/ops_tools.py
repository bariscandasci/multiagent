"""Operasyon mock araçları. Sunucu ve olay kayıtları uydurmadır."""

from __future__ import annotations

from langchain_core.tools import tool

from tools.common import COMPANY, contains_term, fold

SERVERS: list[dict[str, object]] = [
    {
        "name": "api-01",
        "role": "API",
        "status": "healthy",
        "cpu": 42,
        "mem": 61,
        "disk": 48,
        "uptime": "42 gün",
    },
    {
        "name": "db-01",
        "role": "PostgreSQL",
        "status": "degraded",
        "cpu": 88,
        "mem": 91,
        "disk": 77,
        "uptime": "12 gün",
    },
    {
        "name": "web-01",
        "role": "Web",
        "status": "healthy",
        "cpu": 23,
        "mem": 40,
        "disk": 33,
        "uptime": "42 gün",
    },
    {
        "name": "worker-01",
        "role": "Kuyruk işçisi",
        "status": "down",
        "cpu": 0,
        "mem": 0,
        "disk": 51,
        "uptime": "0 gün",
    },
]

INCIDENTS: list[dict[str, str]] = [
    {
        "id": "INC-1844",
        "server": "worker-01",
        "severity": "kritik",
        "status": "open",
        "title": "Heartbeat kaybı",
    },
    {
        "id": "INC-1842",
        "server": "db-01",
        "severity": "yüksek",
        "status": "open",
        "title": "Bellek kullanımı %90 üzerinde",
    },
    {
        "id": "INC-1837",
        "server": "worker-01",
        "severity": "orta",
        "status": "resolved",
        "title": "İşçi süreci yeniden başlatıldı",
    },
]

_STATUS_LABEL = {"healthy": "sağlıklı", "degraded": "bozulmuş", "down": "kapalı"}
_INCIDENT_LABEL = {"open": "açık", "resolved": "çözüldü"}


def _server_by_name(name: str) -> dict[str, object] | None:
    target = fold(name)
    for server in SERVERS:
        if fold(str(server["name"])) == target:
            return server
    return None


def _step_for(server: dict[str, object]) -> str:
    name = server["name"]
    if server["status"] == "down":
        return (
            f"{name} kapalı. Servisi yeniden başlatın, heartbeat alarmını ve son logları kontrol edin, "
            "ardından sağlık kontrolünü tekrarlayın."
        )
    if server["status"] == "degraded":
        return (
            f"{name} bozulmuş durumda (CPU %{server['cpu']}, bellek %{server['mem']}, "
            f"disk %{server['disk']}). En çok kaynak tüketen işleri listeleyin ve alarm eşiğini doğrulayın."
        )
    return f"{name} sağlıklı. Rutin kontrol: yedek, disk doluluğu ve sertifika tarihi."


@tool
def server_status(name: str = "") -> str:
    """Sunucu sağlık, CPU, bellek, disk ve uptime bilgisini döndürür.

    name boşsa tüm sunucular listelenir. Örnek: api-01, db-01, web-01, worker-01.
    """
    requested = (name or "").strip()
    rows = SERVERS
    label = "tümü"
    if requested:
        server = _server_by_name(requested)
        if server is None:
            known = ", ".join(str(item["name"]) for item in SERVERS)
            return f"'{requested}' adlı sunucu yok. Kayıtlı sunucular: {known}."
        rows = [server]
        label = str(server["name"])

    counts = {"healthy": 0, "degraded": 0, "down": 0}
    lines = [f"{COMPANY} sunucu durumu ({label})", ""]
    for server in rows:
        status = str(server["status"])
        counts[status] = counts.get(status, 0) + 1
        lines.append(
            f"- {server['name']} ({server['role']}) — {_STATUS_LABEL.get(status, status)} — "
            f"CPU %{server['cpu']}, bellek %{server['mem']}, disk %{server['disk']}, "
            f"uptime {server['uptime']}"
        )
    lines.append("")
    lines.append(
        f"Özet: {counts.get('healthy', 0)} sağlıklı, "
        f"{counts.get('degraded', 0)} bozulmuş, {counts.get('down', 0)} kapalı."
    )
    return "\n".join(lines)


@tool
def list_incidents(open_only: bool = True) -> str:
    """Operasyon olay kayıtlarını döndürür. open_only doğruysa yalnız açık kayıtlar gelir."""
    rows = [row for row in INCIDENTS if row["status"] == "open"] if open_only else INCIDENTS
    label = "açık" if open_only else "tümü"
    if not rows:
        return "Kayıtlı olay bulunamadı."
    lines = [f"{COMPANY} olay kayıtları ({label})", ""]
    for row in rows:
        lines.append(
            f"- {row['id']} {row['server']} — {row['severity']} — "
            f"{_INCIDENT_LABEL.get(row['status'], row['status'])} — {row['title']}"
        )
    lines.append("")
    lines.append(f"Toplam: {len(rows)}.")
    return "\n".join(lines)


@tool
def plan_technical_tasks(focus: str = "") -> str:
    """Sunucu durumuna göre sıralı bir teknik iş planı üretir.

    focus bir sunucu adıysa o makine plana önce alınır.
    """
    focus_name = (focus or "").strip()
    focus_server = _server_by_name(focus_name) if focus_name else None
    if focus_name and focus_server is None:
        known = ", ".join(str(item["name"]) for item in SERVERS)
        return f"'{focus_name}' adlı sunucu yok. Plan için kayıtlı sunucular: {known}."

    severity = {"down": 0, "degraded": 1, "healthy": 2}
    rest = [server for server in SERVERS if server is not focus_server and server["status"] != "healthy"]
    rest.sort(key=lambda server: severity.get(str(server["status"]), 9))
    chosen: list[dict[str, object]] = []
    if focus_server is not None:
        chosen.append(focus_server)
    chosen.extend(rest)
    if not chosen:
        chosen = list(SERVERS)

    lines = [f"{COMPANY} teknik iş planı", ""]
    for index, server in enumerate(chosen, start=1):
        lines.append(f"{index}. {_step_for(server)}")
    open_rows = [row for row in INCIDENTS if row["status"] == "open"]
    if open_rows:
        lines.append("")
        lines.append("Bağlı açık olaylar:")
        for row in open_rows:
            lines.append(f"- {row['id']} {row['server']}: {row['title']} ({row['severity']})")
    return "\n".join(lines)


def known_server(text: str) -> str:
    folded = fold(text)
    for server in SERVERS:
        if contains_term(folded, fold(str(server["name"]))):
            return str(server["name"])
    return ""


OPS_TOOLS = [server_status, list_incidents, plan_technical_tasks]

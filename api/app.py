"""FastAPI uygulaması ve komuta merkezi."""

from __future__ import annotations

import base64
import json
import queue
import secrets
import threading
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse

from agents.catalog import AGENTS
from agents.context import add_note, agent_settings, delete_note, memory_notes, save_agents
from agents.progress import bind_progress, reset_progress
from api.email_draft import draft_sales_email
from api.pdf_export import build_proposal_pdf, pdf_filename
from api.report import split_report
from api.schemas import (
    AgentConfigDocument,
    AgentConfigUpdate,
    AgentDirective,
    AgentInfo,
    ChatRequest,
    ChatResponse,
    ExpenseCreate,
    ExpenseRow,
    EmailDraftRequest,
    EmailDraftResponse,
    ExpenseUpdate,
    HealthResponse,
    KnowledgeDocument,
    KnowledgeLibrary,
    LedgerResponse,
    MemoryCreate,
    MemoryDocument,
    MemoryNote,
    Opportunity,
    OpportunityCreate,
    OpportunityUpdate,
    CrmDocument,
    PdfExportRequest,
    ProjectDetail,
    ProjectSummary,
    ReportSections,
)
from config import admin_credentials, get_settings
from memory.session import Orchestrator, get_orchestrator

APP_VERSION = "1.0.0"
PUBLIC_PATHS = {"/api/health", "/robots.txt"}
ROBOTS_TXT = "User-agent: *\nDisallow: /\n"
from tools.analysis import build_market_section, build_rnd_section
from tools.crm import create_opportunity, delete_opportunity, list_opportunities, update_opportunity
from tools.finance_tools import (
    add_expense,
    delete_expense_row,
    get_monthly_expenses,
    ledger_totals,
    load_ledger,
    simulate_project_budget,
    update_expense_row,
)
from tools.github_tools import PROJECTS_DIR, list_projects, load_project
from tools.knowledge import KnowledgeError, add_document, delete_document, list_documents

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "static" / "index.html"


def _sections_for(answer: str, department: str) -> ReportSections:
    return ReportSections(**split_report(answer, department))


def _chat_payload(result: dict) -> ChatResponse:
    return ChatResponse(
        **result,
        sections=_sections_for(result.get("answer") or "", result.get("department") or ""),
    )


def _row(item: dict, *, project: str = "") -> ExpenseRow:
    return ExpenseRow(
        id=str(item.get("id") or ""),
        name=str(item.get("name") or ""),
        category=str(item.get("category") or ""),
        amount=float(item.get("amount") or 0),
        project=str(item.get("project") or project),
    )


def _ledger(message: str = "") -> LedgerResponse:
    payload = load_ledger()
    fixed = [_row(item) for item in payload.get("fixed_monthly") or []]
    projects = [_row(item) for item in payload.get("project_costs") or []]
    totals = ledger_totals(payload)
    income = [_row(item) for item in payload.get("income") or []]
    return LedgerResponse(
        company=str(payload.get("company") or "BCD TECHNOLOGIES"),
        currency=str(payload.get("currency") or "TRY"),
        fixed_monthly=fixed,
        project_costs=projects,
        income=income,
        message=message,
        **totals,
    )


def _summary(record: dict) -> ProjectSummary:
    return ProjectSummary(
        slug=str(record.get("slug") or ""),
        owner=str(record.get("owner") or ""),
        repo=str(record.get("repo") or ""),
        description=str(record.get("description") or ""),
        url=str(record.get("url") or ""),
        fetched_at=str(record.get("fetched_at") or ""),
    )


def _read_record(slug: str) -> dict:
    if not slug or Path(slug).name != slug or "/" in slug or "\\" in slug:
        raise HTTPException(status_code=404, detail="Proje bulunamadı")
    record = load_project(slug)
    if record is None or str(record.get("slug") or "") != slug:
        path = PROJECTS_DIR / f"{slug}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Proje bulunamadı")
        record = json.loads(path.read_text(encoding="utf-8"))
    if str(record.get("slug") or "") != slug:
        raise HTTPException(status_code=404, detail="Proje bulunamadı")
    return record


def _project_detail(record: dict) -> ProjectDetail:
    slug = str(record.get("slug") or "")
    project_name = f"{record.get('owner')}/{record.get('repo')}"
    finance = "\n\n".join(
        [
            str(get_monthly_expenses.invoke({})),
            str(
                simulate_project_budget.invoke(
                    {
                        "project": project_name,
                        "monthly_price": 0,
                        "extra_monthly_cost": 0,
                        "note": "kayıtlı proje",
                    }
                )
            ),
        ]
    )
    description = str(record.get("description") or "").strip()
    executive = f"{record.get('owner')}/{record.get('repo')}\n\n{description or 'Kayıtlı depo özeti.'}"
    return ProjectDetail(
        project=_summary(record),
        sections=ReportSections(
            executive=executive,
            market=build_market_section(slug),
            rnd=build_rnd_section(slug),
            finance=finance,
        ),
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _agent_catalog() -> dict[str, dict]:
    return {agent["id"]: agent for agent in AGENTS}


def _config_document() -> AgentConfigDocument:
    catalog = _agent_catalog()
    rows = []
    for agent_id in ("supervisor", "market", "rnd", "finance"):
        meta = catalog[agent_id]
        saved = agent_settings(agent_id)
        rows.append(
            AgentDirective(
                id=agent_id,
                name=meta["name"],
                description=meta["description"],
                directive=saved["directive"],
                temperature=saved["temperature"],
            )
        )
    return AgentConfigDocument(agents=rows)


def _apply_expense(message: str) -> LedgerResponse:
    if message.startswith("Hata: gider bulunamadı"):
        raise HTTPException(status_code=404, detail=message)
    if message.startswith("Hata"):
        raise HTTPException(status_code=422, detail=message)
    return _ledger(message)


class RobotsTagMiddleware:
    """Her HTTP yanıtına arama motoru yasağı ekler. Auth 401 yanıtları da dahil."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_tagged(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-robots-tag", b"noindex, nofollow"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_tagged)


class AdminAuthMiddleware:
    """ASGI katmanı. BaseHTTPMiddleware akışı tamponladığı için kullanılmaz."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        expected = admin_credentials()
        if expected is None:
            await self.app(scope, receive, send)
            return
        header = ""
        for key, value in scope.get("headers") or []:
            if key.lower() == b"authorization":
                header = value.decode("latin-1")
                break
        username, password = _basic_credentials(header)
        if _same_secret(username, expected[0]) and _same_secret(password, expected[1]):
            await self.app(scope, receive, send)
            return
        body = "Kimlik doğrulaması gerekli.".encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    [b"content-type", b"text/plain; charset=utf-8"],
                    [b"www-authenticate", b'Basic realm="BCD TECHNOLOGIES"'],
                    [b"content-length", str(len(body)).encode()],
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _same_secret(given: str, expected: str) -> bool:
    if len(given) != len(expected):
        return False
    return secrets.compare_digest(given, expected)


def _basic_credentials(header: str) -> tuple[str, str]:
    if not header.lower().startswith("basic "):
        return "", ""
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1].strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return "", ""
    username, separator, password = decoded.partition(":")
    if not separator:
        return "", ""
    return username, password


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    app = FastAPI(
        title="BCD TECHNOLOGIES — Çoklu Ajan Komuta Merkezi",
        version=APP_VERSION,
        summary="Yönetici ajan GitHub deposunu pazar, Ar-Ge ve finans uzmanlarıyla tek raporda toplar.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AdminAuthMiddleware)
    app.add_middleware(RobotsTagMiddleware)
    runner = orchestrator or get_orchestrator()

    @app.get("/robots.txt", include_in_schema=False)
    def robots() -> PlainTextResponse:
        return PlainTextResponse(ROBOTS_TXT, media_type="text/plain")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(INDEX, headers={"Cache-Control": "no-cache"})

    @app.get("/api/health", response_model=HealthResponse, tags=["sistem"])
    def health() -> HealthResponse:
        settings = get_settings()
        return HealthResponse(
            status="ok",
            version=APP_VERSION,
            llm_configured=settings.configured,
            provider=settings.provider,
            model=settings.model,
            agents=[AgentInfo(**agent) for agent in AGENTS],
        )

    @app.get("/api/agents", response_model=list[AgentInfo], tags=["sistem"])
    def agents() -> list[AgentInfo]:
        return [AgentInfo(**agent) for agent in AGENTS]

    @app.post("/api/chat", response_model=ChatResponse, tags=["sohbet"])
    def chat(payload: ChatRequest) -> ChatResponse:
        return _chat_payload(runner.ask(payload.message, payload.session_id))

    @app.post("/api/chat/stream", tags=["sohbet"])
    def chat_stream(payload: ChatRequest) -> StreamingResponse:
        def events():
            yield _sse({"phase": "supervisor", "id": "supervisor", "label": "Yönetici isteği ayırıyor", "status": "running"})
            mailbox: queue.Queue = queue.Queue()
            holder: dict = {}

            def work() -> None:
                token = bind_progress(mailbox.put)
                try:
                    holder["result"] = runner.ask(payload.message, payload.session_id)
                except Exception:
                    holder["result"] = {
                        "session_id": payload.session_id or "",
                        "department": "supervisor",
                        "route": "general",
                        "reason": "error",
                        "mode": "mock",
                        "tools_used": [],
                        "answer": "İstek işlenirken bir hata oluştu. Lütfen yeniden deneyin.",
                        "trace": [],
                    }
                finally:
                    reset_progress(token)
                    mailbox.put(None)

            threading.Thread(target=work, daemon=True).start()
            while True:
                try:
                    item = mailbox.get(timeout=10)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                if item is None:
                    break
                yield _sse(item)
            body = _chat_payload(holder["result"]).model_dump()
            for tool in body["tools_used"]:
                yield _sse(
                    {
                        "phase": "tool",
                        "tool": tool,
                        "department": body["department"],
                        "label": tool,
                    }
                )
            yield _sse({"phase": "done", **body})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/projects", response_model=list[ProjectSummary], tags=["projeler"])
    def projects() -> list[ProjectSummary]:
        found: list[ProjectSummary] = []
        for path in reversed(list_projects()):
            record = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(record, dict):
                found.append(_summary(record))
        return found

    @app.get("/api/projects/{slug}", response_model=ProjectDetail, tags=["projeler"])
    def project_detail(slug: str) -> ProjectDetail:
        return _project_detail(_read_record(slug))

    @app.get("/api/expenses", response_model=LedgerResponse, tags=["finans"])
    def expenses() -> LedgerResponse:
        return _ledger()

    @app.post("/api/expenses", response_model=LedgerResponse, tags=["finans"])
    def create_expense(payload: ExpenseCreate) -> LedgerResponse:
        message = str(
            add_expense.invoke(
                {
                    "name": payload.name,
                    "amount": payload.amount,
                    "category": payload.category,
                    "project": payload.project,
                }
            )
        )
        if message.startswith("Hata"):
            raise HTTPException(status_code=422, detail=message)
        return _ledger(message)

    @app.patch("/api/expenses/{expense_id}", response_model=LedgerResponse, tags=["finans"])
    def update_expense(expense_id: str, payload: ExpenseUpdate) -> LedgerResponse:
        fields = payload.model_dump(exclude_unset=True)
        return _apply_expense(update_expense_row(expense_id, **fields))

    @app.delete("/api/expenses/{expense_id}", response_model=LedgerResponse, tags=["finans"])
    def remove_expense(expense_id: str) -> LedgerResponse:
        return _apply_expense(delete_expense_row(expense_id))

    @app.get("/api/agents/config", response_model=AgentConfigDocument, tags=["ajanlar"])
    def read_agent_config() -> AgentConfigDocument:
        return _config_document()

    @app.post("/api/agents/config", response_model=AgentConfigDocument, tags=["ajanlar"])
    def write_agent_config(payload: AgentConfigUpdate) -> AgentConfigDocument:
        ids = [agent.id for agent in payload.agents]
        if set(ids) != {"supervisor", "market", "rnd", "finance"}:
            raise HTTPException(status_code=422, detail="Dört ajanın tamamı gerekli.")
        save_agents([agent.model_dump() for agent in payload.agents])
        return _config_document()

    @app.get("/api/knowledge", response_model=KnowledgeLibrary, tags=["bilgi-bankasi"])
    def read_knowledge() -> KnowledgeLibrary:
        return KnowledgeLibrary(documents=[KnowledgeDocument(**row) for row in list_documents()])

    @app.post("/api/knowledge/upload", response_model=KnowledgeDocument, tags=["bilgi-bankasi"])
    async def upload_knowledge(
        file: UploadFile = File(...),
        department: str = Form("all"),
    ) -> KnowledgeDocument:
        payload = await file.read()
        try:
            saved = add_document(file.filename or "dokuman.txt", department, payload)
        except KnowledgeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return KnowledgeDocument(**saved)

    @app.delete("/api/knowledge/{doc_id}", response_model=KnowledgeLibrary, tags=["bilgi-bankasi"])
    def remove_knowledge(doc_id: str) -> KnowledgeLibrary:
        if not delete_document(doc_id):
            raise HTTPException(status_code=404, detail="Doküman bulunamadı.")
        return read_knowledge()

    @app.get("/api/memory", response_model=MemoryDocument, tags=["hafiza"])
    def read_memory() -> MemoryDocument:
        return MemoryDocument(notes=[MemoryNote(**note) for note in memory_notes()])

    @app.post("/api/memory", response_model=MemoryDocument, tags=["hafiza"])
    def create_memory(payload: MemoryCreate) -> MemoryDocument:
        add_note(payload.text)
        return MemoryDocument(notes=[MemoryNote(**note) for note in memory_notes()])

    @app.delete("/api/memory/{note_id}", response_model=MemoryDocument, tags=["hafiza"])
    def remove_memory(note_id: str) -> MemoryDocument:
        if not delete_note(note_id):
            raise HTTPException(status_code=404, detail="Hafıza kaydı bulunamadı.")
        return MemoryDocument(notes=[MemoryNote(**note) for note in memory_notes()])

    @app.get("/api/crm", response_model=CrmDocument, tags=["crm"])
    def read_crm() -> CrmDocument:
        body = list_opportunities()
        return CrmDocument(
            opportunities=[Opportunity(**row) for row in body["opportunities"]],
            pipeline_total=body["pipeline_total"],
            pipeline_currency=body["pipeline_currency"],
        )

    @app.post("/api/crm", response_model=Opportunity, tags=["crm"])
    def create_crm(payload: OpportunityCreate) -> Opportunity:
        try:
            row = create_opportunity(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return Opportunity(**row)

    @app.patch("/api/crm/{opportunity_id}", response_model=Opportunity, tags=["crm"])
    def update_crm(opportunity_id: str, payload: OpportunityUpdate) -> Opportunity:
        try:
            row = update_opportunity(opportunity_id, payload.model_dump(exclude_unset=True))
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Fırsat bulunamadı") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return Opportunity(**row)

    @app.delete("/api/crm/{opportunity_id}", response_model=CrmDocument, tags=["crm"])
    def remove_crm(opportunity_id: str) -> CrmDocument:
        try:
            delete_opportunity(opportunity_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Fırsat bulunamadı") from exc
        return read_crm()

    @app.post("/api/export/pdf", tags=["rapor"])
    def export_pdf(payload: PdfExportRequest) -> Response:
        document = build_proposal_pdf(payload.project_name, payload.sections.model_dump())
        filename = pdf_filename(payload.project_name)
        disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
        return Response(content=document, media_type="application/pdf", headers={"Content-Disposition": disposition})

    @app.post("/api/agents/draft-email", response_model=EmailDraftResponse, tags=["ajanlar"])
    def draft_email(payload: EmailDraftRequest) -> EmailDraftResponse:
        drafted = draft_sales_email(payload.project_name, payload.customer_profile, payload.sections.model_dump())
        return EmailDraftResponse(**drafted)

    return app


app = create_app()

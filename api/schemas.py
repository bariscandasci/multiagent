"""HTTP şemaları."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=64)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("message boş olamaz")
        return cleaned


class ReportSections(BaseModel):
    executive: str = ""
    market: str = ""
    rnd: str = ""
    finance: str = ""


class TraceStep(BaseModel):
    id: str
    label: str
    tools: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    status: str = "done"


class ChatResponse(BaseModel):
    session_id: str
    department: str
    route: str
    reason: str
    mode: str
    tools_used: list[str]
    answer: str
    sections: ReportSections
    trace: list[TraceStep] = Field(default_factory=list)


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_configured: bool
    provider: str
    model: str
    agents: list[AgentInfo]


class ExpenseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    amount: float = Field(..., ge=0)
    category: str = Field(default="", max_length=40)
    project: str = Field(default="", max_length=80)

    @field_validator("name", "category", "project")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ExpenseRow(BaseModel):
    id: str
    name: str
    category: str
    amount: float
    project: str = ""


class LedgerResponse(BaseModel):
    company: str
    currency: str
    fixed_monthly: list[ExpenseRow]
    project_costs: list[ExpenseRow]
    fixed_total: float
    project_total: float
    monthly_total: float = 0
    target_profit: float = 0
    realized_income: float = 0
    income: list[ExpenseRow] = Field(default_factory=list)
    message: str = ""


class ExpenseUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    amount: float | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, max_length=40)
    project: str | None = Field(default=None, max_length=80)

    @field_validator("name", "category", "project")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class AgentDirective(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    directive: str = Field(default="", max_length=8000)
    temperature: float = Field(default=0, ge=0, le=2)


class AgentConfigDocument(BaseModel):
    agents: list[AgentDirective]


class AgentConfigUpdate(BaseModel):
    agents: list[AgentDirective] = Field(..., min_length=4, max_length=4)


class MemoryNote(BaseModel):
    id: str
    text: str
    created_at: str


class MemoryDocument(BaseModel):
    notes: list[MemoryNote]


class MemoryCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("hafıza metni gerekli")
        return cleaned


class ProjectSummary(BaseModel):
    slug: str
    owner: str
    repo: str
    description: str
    url: str
    fetched_at: str


class ProjectDetail(BaseModel):
    project: ProjectSummary
    sections: ReportSections


class PdfExportRequest(BaseModel):
    project_name: str = Field(default="", max_length=160)
    sections: ReportSections = Field(default_factory=ReportSections)

    @field_validator("project_name")
    @classmethod
    def strip_project(cls, value: str) -> str:
        return value.strip()


class EmailDraftRequest(BaseModel):
    project_name: str = Field(default="", max_length=160)
    customer_profile: str = Field(..., max_length=500)
    sections: ReportSections = Field(default_factory=ReportSections)

    @field_validator("project_name")
    @classmethod
    def strip_project_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("customer_profile")
    @classmethod
    def profile_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("müşteri profili gerekli")
        return cleaned


class EmailDraftResponse(BaseModel):
    subject: str
    body: str
    mode: str
    model: str = ""


class Opportunity(BaseModel):
    id: str
    musteri_adi: str
    proje_basligi: str = ""
    teklif_tutari: float = 0
    para_birimi: str = "TRY"
    durum: str
    olusturma_tarihi: str
    notlar: str = ""


class CrmDocument(BaseModel):
    opportunities: list[Opportunity]
    pipeline_total: float = 0
    pipeline_currency: str = "TRY"


class OpportunityCreate(BaseModel):
    musteri_adi: str = Field(..., min_length=2, max_length=160)
    proje_basligi: str = Field(default="", max_length=160)
    teklif_tutari: float = Field(default=0, ge=0)
    para_birimi: str = Field(default="TRY", max_length=8)
    durum: str = "Taslak"
    notlar: str = Field(default="", max_length=2000)

    @field_validator("musteri_adi", "proje_basligi", "para_birimi", "notlar")
    @classmethod
    def strip_crm_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("durum")
    @classmethod
    def known_status(cls, value: str) -> str:
        from tools.crm import STATUSES

        cleaned = value.strip()
        if cleaned not in STATUSES:
            raise ValueError("durum geçersiz")
        return cleaned


class OpportunityUpdate(BaseModel):
    musteri_adi: str | None = Field(default=None, max_length=160)
    proje_basligi: str | None = Field(default=None, max_length=160)
    teklif_tutari: float | None = Field(default=None, ge=0)
    para_birimi: str | None = Field(default=None, max_length=8)
    durum: str | None = None
    notlar: str | None = Field(default=None, max_length=2000)

    @field_validator("musteri_adi", "proje_basligi", "para_birimi", "notlar")
    @classmethod
    def strip_optional_crm(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("durum")
    @classmethod
    def known_optional_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from tools.crm import STATUSES

        cleaned = value.strip()
        if cleaned not in STATUSES:
            raise ValueError("durum geçersiz")
        return cleaned

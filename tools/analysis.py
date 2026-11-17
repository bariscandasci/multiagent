"""Kaydedilmiş depodan pazar ve Ar-Ge metni üretir. LLM yokken aynı başlıklar kullanılır."""

from __future__ import annotations

from tools.common import COMPANY, fold
from tools.github_tools import load_project

SECTORS = (
    (("belediye", "kamu", "e-devlet", "ankar"), "Kamu ve yerel yönetimler", "kurumsal", "dijital dönüşüm yöneticisi, daire başkanı"),
    (("banka", "finans", "odeme", "sigorta"), "Finansal hizmetler", "orta ve büyük ölçek", "CTO, dijital kanallar müdürü"),
    (("saglik", "hastane", "klinik"), "Sağlık", "orta ölçek ve kurum", "başhekim, bilgi işlem müdürü"),
    (("egitim", "okul", "universite"), "Eğitim", "okul ve orta ölçek", "kurum müdürü, eğitim teknolojileri sorumlusu"),
    (("eticaret", "e-ticaret", "perakende", "magaza"), "Perakende ve e-ticaret", "KOBİ ve orta ölçek", "e-ticaret müdürü, işletme sahibi"),
)


def _blob(record: dict) -> str:
    parts = [
        str(record.get("description") or ""),
        str(record.get("readme") or ""),
        " ".join(record.get("tree") or []),
        " ".join(f"{name}\n{content}" for name, content in (record.get("dependencies") or {}).items()),
    ]
    return fold("\n".join(parts))


def _stack(record: dict) -> list[str]:
    blob = _blob(record)
    names = (
        ("fastapi", "FastAPI"),
        ("django", "Django"),
        ("flask", "Flask"),
        ("react", "React"),
        ("next", "Next.js"),
        ("vue", "Vue"),
        ("langchain", "LangChain"),
        ("openai", "OpenAI"),
        ("tensorflow", "TensorFlow"),
        ("pytorch", "PyTorch"),
        ("postgres", "PostgreSQL"),
        ("docker", "Docker"),
    )
    found = [label for needle, label in names if needle in blob]
    language = str(record.get("language") or "").strip()
    if language and language not in found:
        found.insert(0, language)
    return found


def build_market_section(query: str = "") -> str:
    record = load_project(query)
    if record is None:
        return (
            f"{COMPANY} — Operasyon & Pazar Geliştirme\n\n"
            "Kayıtlı proje yok. Satış profili çıkarabilmem için bir GitHub deposu verin."
        )
    blob = _blob(record)
    matches = [item for item in SECTORS if any(needle in blob for needle in item[0])]
    if not matches:
        matches = [((), "Yazılım ürünü kullanan işletmeler", "KOBİ ve orta ölçek", "genel müdür, CTO, operasyon müdürü")]
    stack = ", ".join(_stack(record)) or "depoya göre netleşmedi"
    description = str(record.get("description") or "").strip() or "README içindeki ürün vaadi"
    lines = [
        f"{COMPANY} — Operasyon & Pazar Geliştirme",
        f"Proje: {record.get('owner')}/{record.get('repo')}",
        "",
        "Potansiyel müşteri profilleri:",
    ]
    for _, sector, scale, buyers in matches:
        lines.append(f"- Sektör: {sector}. Ölçek: {scale}. Karar verici: {buyers}.")
    lines.extend(
        [
            "",
            "Değer önerisi:",
            f"{description} Yığın: {stack}. {COMPANY} bu depoyu sektöre özel bir teklife çevirir; alıcı hazır ürün değil, kendi iş akışına uyan bir teslimat görür.",
            "",
            "Satış stratejisi:",
            "1. Karar vericiyle 30 dakikalık keşif görüşmesi yapın; mevcut operasyon maliyetini sorun.",
            "2. Deponun çalışan bir dilimini pilot kapsam olarak tanımlayıp 4 haftalık deneme teklif edin.",
            "3. Pilot sonucunu aynı sektörden ikinci müşteri için referans dosyasına bağlayın.",
        ]
    )
    return "\n".join(lines)


def build_rnd_section(query: str = "") -> str:
    record = load_project(query)
    if record is None:
        return (
            f"{COMPANY} — Teknik & Ar-Ge\n\n"
            "Kayıtlı proje yok. Teknik yol haritası için bir GitHub deposu verin."
        )
    blob = _blob(record)
    tree = [str(path) for path in record.get("tree") or []]
    stack = _stack(record)
    has_tests = any("test" in path.lower() for path in tree)
    has_ci = any(path.startswith(".github/workflows/") for path in tree)
    has_ai = any(name in blob for name in ("langchain", "openai", "transformers", "tensorflow", "pytorch"))
    suggestions = []
    if not has_tests:
        suggestions.append("pytest veya deponun diline uygun test koşucusunu ekleyin; kritik akışa ilk testi yazın.")
    if not has_ci:
        suggestions.append("GitHub Actions ile kurulum, test ve bağımlılık denetimini her push'ta çalıştırın.")
    if not has_ai:
        suggestions.append("Kullanıcı metnini özetleyen dar bir yapay zeka adımı ekleyin; modeli mevcut API katmanının arkasına alın.")
    if "docker" not in blob:
        suggestions.append("Tekrarlanabilir çalıştırma için Dockerfile ve örnek ortam değişkeni dosyası ekleyin.")
    if not suggestions:
        suggestions.append("Mevcut test ve CI üzerine sektör senaryolarını ölçen bir değerlendirme seti ekleyin.")
    libraries = []
    if any(name in ("Python", "FastAPI", "Django", "Flask") for name in stack) or "python" in blob:
        libraries.append("pydantic ve httpx (sözleşme ve dış API)")
    if not has_ai:
        libraries.append("resmi model SDK'sı, yalnızca tek bir kullanım senaryosu için")
    if not libraries:
        libraries.append("mevcut bağımlılıkların güncel yama sürümleri")
    feature = "rakip ürünlerde dağınık kalan iş akışını depodaki mevcut verilere bağlayan bir karar ekranı"
    lines = [
        f"{COMPANY} — Teknik & Ar-Ge",
        f"Proje: {record.get('owner')}/{record.get('repo')}",
        f"Görünen yığın: {', '.join(stack) or 'bağımlılık dosyasından çıkmadı'}.",
        f"Ayırıcı özellik adayı: {feature}.",
        "",
        "Önerilen kütüphaneler:",
        *[f"- {item}" for item in libraries],
        "",
        "Ar-Ge yol haritası:",
        "1. README ve bağımlılık dosyasındaki çalıştırma adımını tek komuta indirin.",
        f"2. {suggestions[0]}",
        "3. Ayırıcı özelliği mevcut modül sınırının içinde, yeni bir servis açmadan prototipleyin.",
        "4. Pilot müşterinin verisiyle ölçüyü alın; ancak ondan sonra modeli veya altyapıyı büyütün.",
    ]
    return "\n".join(lines)

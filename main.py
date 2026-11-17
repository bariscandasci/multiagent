"""Terminal sohbeti ve API giriş noktası."""

from __future__ import annotations

import argparse
from uuid import uuid4

from config import get_settings
from memory.session import get_orchestrator

DEPARTMENT_LABELS = {
    "hr": "İK",
    "finance": "Finans",
    "ops": "Operasyon",
    "supervisor": "Yönetici",
}

SAMPLES = (
    "Personel listesini ve açık adayları çıkar",
    "Son çeyrek gelir gider özeti ve geciken faturalar",
    "Sunucu durumunu kontrol et ve teknik iş planı çıkar",
)


def _print_result(result: dict) -> None:
    label = DEPARTMENT_LABELS.get(result["department"], result["department"])
    tools = ", ".join(result["tools_used"]) or "araç yok"
    print(f"[{label} | {result['mode']} | {result['reason']} | {tools}]")
    print(result["answer"])
    print()


def cmd_chat() -> None:
    settings = get_settings()
    mode = settings.provider if settings.configured else "mock"
    session_id = uuid4().hex
    print(f"Çoklu ajan sohbeti hazır (mod: {mode}). Çıkış: /exit  Yeni oturum: /reset")
    orchestrator = get_orchestrator()
    while True:
        try:
            text = input("Siz> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        if text.lower() in {"/exit", "/quit", "cik", "çık"}:
            return
        if text.lower() == "/reset":
            session_id = uuid4().hex
            print("Yeni oturum başlatıldı.")
            continue
        _print_result(orchestrator.ask(text, session_id))


def cmd_ask(message: str, session: str) -> None:
    _print_result(get_orchestrator().ask(message, session))


def cmd_demo() -> None:
    orchestrator = get_orchestrator()
    for index, message in enumerate(SAMPLES, start=1):
        print(f"Siz> {message}")
        _print_result(orchestrator.ask(message, f"demo-{index}"))


def cmd_serve(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run("api.app:app", host=host, port=port, reload=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Şirket içi çoklu ajan sistemi")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("chat", help="Terminal sohbeti")
    sub.add_parser("demo", help="Üç örnek isteği çalıştır")
    ask = sub.add_parser("ask", help="Tek bir istek gönder")
    ask.add_argument("message")
    ask.add_argument("--session", default="cli")
    serve = sub.add_parser("serve", help="FastAPI sunucusunu başlat")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "chat":
        cmd_chat()
    elif args.command == "demo":
        cmd_demo()
    elif args.command == "ask":
        cmd_ask(args.message, args.session)
    elif args.command == "serve":
        cmd_serve(args.host, args.port)
    else:
        parser.error(f"Bilinmeyen komut: {args.command}")


if __name__ == "__main__":
    main()

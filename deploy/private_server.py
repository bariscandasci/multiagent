"""Uvicorn'u tek süreçte yalnız loopback ve BIND_IP üzerinde açar."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from deploy.bind import listen_hosts

PORT = 8000
ROOT = Path(__file__).resolve().parents[1]


def _open_socket(host: str) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, PORT))
    return sock


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    hosts = listen_hosts(os.environ.get("BIND_IP", "127.0.0.1"))
    sockets = [_open_socket(host) for host in hosts]
    config = uvicorn.Config("api.app:app", host="127.0.0.1", port=PORT, workers=1, log_level="info")
    uvicorn.Server(config).run(sockets=sockets)


if __name__ == "__main__":
    main()

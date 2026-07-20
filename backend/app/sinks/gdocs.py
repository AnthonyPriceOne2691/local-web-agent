"""Google Docs sink (Tier 0, doc 25 § Credentials): экспорт результата в Google Doc.

Переиспользует OAuth-авторизацию из референс-папки `Gdocs-tabs editor` (credentials.json +
token.json, gitignored) — через `refresh_token`, без повторного логина. Логика та же, что в
Node-решении `run.js`: авторизация → docs.documents.create → batchUpdate insertText.

Google-библиотеки — опциональный extra (`uv sync --extra gdocs`), импортируются лениво:
сервис работает без них, sink недоступен → GdocsUnavailable. Облако: экспорт наружу — это
сознательное действие с consent (cloud carve-out, doc 25), а не молчаливая телеметрия.
"""

from __future__ import annotations

import json
from pathlib import Path

# scopes минимально нужные для «создать документ и записать текст» (token их покрывает)
DOCS_SCOPES = (
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
)


class GdocsUnavailable(RuntimeError):
    """google-либы не установлены, либо креды/токен отсутствуют/без refresh_token."""


def _load_credentials(credentials_path: Path, token_path: Path):
    """OAuth Credentials из credentials.json (client_id/secret) + token.json (refresh_token).

    Тот же формат creds/token, что использует Node `run.js` — переиспользуем как есть.
    """
    try:
        from google.oauth2.credentials import Credentials
    except ImportError as exc:  # extra не установлен
        raise GdocsUnavailable("google-auth не установлен — `uv sync --extra gdocs`") from exc

    for p in (credentials_path, token_path):
        if not p.exists():
            raise GdocsUnavailable(f"не найден {p} (референс-папка Google Docs, gitignored)")

    client = json.loads(credentials_path.read_text(encoding="utf-8"))
    client = client.get("installed") or client.get("web") or {}
    tok = json.loads(token_path.read_text(encoding="utf-8"))
    if not tok.get("refresh_token"):
        raise GdocsUnavailable("token.json без refresh_token — нужна повторная авторизация в Node-решении")

    return Credentials(
        token=tok.get("access_token"),
        refresh_token=tok["refresh_token"],
        token_uri=client.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=client.get("client_id"),
        client_secret=client.get("client_secret"),
        scopes=list(DOCS_SCOPES),
    )


def export_to_doc(title: str, text: str, *, credentials_path: Path, token_path: Path) -> str:
    """Создать Google Doc `title` с телом `text`, вернуть его URL.

    Переиспользует логику run.js (createDoc + insertText). refresh_token обновляет
    access_token сам, без консента. Бросает GdocsUnavailable, если sink недоступен.
    """
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GdocsUnavailable("google-api-python-client не установлен — `uv sync --extra gdocs`") from exc

    creds = _load_credentials(credentials_path, token_path)
    if not creds.valid:  # access_token протух → обновляем по refresh_token
        from google.auth.transport.requests import Request

        creds.refresh(Request())

    docs = build("docs", "v1", credentials=creds, cache_discovery=False)
    doc_id = docs.documents().create(body={"title": title}).execute()["documentId"]
    if text:
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]},
        ).execute()
    return f"https://docs.google.com/document/d/{doc_id}/edit"

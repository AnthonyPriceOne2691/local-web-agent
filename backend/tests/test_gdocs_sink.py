"""Google Docs sink (doc 25 Tier 0): auth-reuse + create+insert (mocked google client).

Google-либы — optional extra `gdocs`; без них тесты пропускаются (sink недоступен).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("googleapiclient")  # extra `gdocs` не установлен → пропустить
pytest.importorskip("google.oauth2.credentials")

from app.sinks.gdocs import GdocsUnavailable, _load_credentials, export_to_doc


def _write_creds(tmp_path, *, refresh: bool = True):
    (tmp_path / "credentials.json").write_text(json.dumps(
        {"web": {"client_id": "x", "client_secret": "y", "token_uri": "u"}}), encoding="utf-8")
    tok = {"access_token": "a"}
    if refresh:
        tok["refresh_token"] = "r"
    (tmp_path / "token.json").write_text(json.dumps(tok), encoding="utf-8")
    return tmp_path / "credentials.json", tmp_path / "token.json"


def test_unavailable_when_files_missing(tmp_path):
    with pytest.raises(GdocsUnavailable):
        _load_credentials(tmp_path / "nope.json", tmp_path / "no.json")


def test_unavailable_without_refresh_token(tmp_path):
    creds, token = _write_creds(tmp_path, refresh=False)
    with pytest.raises(GdocsUnavailable, match="refresh_token"):
        _load_credentials(creds, token)


def test_export_builds_create_then_insert(tmp_path, monkeypatch):
    creds, token = _write_creds(tmp_path)
    calls: dict = {}

    class _Exec:
        def __init__(self, ret): self._ret = ret
        def execute(self): return self._ret

    class _Docs:
        def create(self, body):
            calls["create"] = body
            return _Exec({"documentId": "DOC1"})

        def batchUpdate(self, documentId, body):
            calls["batch"] = (documentId, body)
            return _Exec({})

    class _Service:
        def documents(self): return _Docs()

    # creds уже валидны (без refresh) + google-клиент замокан
    monkeypatch.setattr("app.sinks.gdocs._load_credentials",
                        lambda c, t: type("C", (), {"valid": True})())
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **k: _Service())

    url = export_to_doc("Report", "Body text here",
                        credentials_path=creds, token_path=token)
    assert url == "https://docs.google.com/document/d/DOC1/edit"
    assert calls["create"] == {"title": "Report"}
    assert calls["batch"][0] == "DOC1"
    assert calls["batch"][1]["requests"][0]["insertText"]["text"] == "Body text here"
    assert calls["batch"][1]["requests"][0]["insertText"]["location"]["index"] == 1

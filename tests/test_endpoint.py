import json

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app import monday
from app.main import app

LONG_NAME = (
    "Zweckverband Gemeinschaftliche Wasserversorgung und Abwasserentsorgung "
    "Landkreis Oberallgäu Süd Kempten Immenstadt"
)
BODY = {"payload": {"inputFields": {"boardId": 1, "itemId": 42}}}


def auth(secret: str = "test-signing-secret-0123456789abcdef") -> dict:
    token = jwt.encode({"accountId": 1, "userId": 2}, secret, algorithm="HS256")
    return {"Authorization": token}


@pytest.fixture
def fake_monday(monkeypatch):
    """Replaces the monday API with an in-memory board and records mutations."""
    state = {
        "text_mkt92ar9": LONG_NAME, "text_mksb1npw": "", "mutations": [], "calls": 0,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        assert request.headers["Authorization"] == "test-api-token"
        payload = json.loads(request.content)
        if "mutation" in payload["query"]:
            values = json.loads(payload["variables"]["values"])
            state["mutations"].append(values)
            state.update(values)
            return httpx.Response(200, json={"data": {"change_multiple_column_values": {"id": "42"}}})
        cols = [
            {"id": c, "type": "text", "text": state[c]}
            for c in payload["variables"]["colIds"] if c in state
        ]
        return httpx.Response(200, json={"data": {"items": [{"name": "Item", "column_values": cols}]}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        monday.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    return state


client = TestClient(app)


def test_splits_long_name_and_writes_both_columns(fake_monday):
    res = client.post("/monday/split-name", json=BODY, headers=auth())
    assert res.status_code == 200
    assert fake_monday["mutations"] == [
        {
            "text_mkt92ar9": "Zweckverband Gemeinschaftliche Wasserversorgung und "
            "Abwasserentsorgung Landkreis Oberallgäu Süd",
            "text_mksb1npw": "Kempten Immenstadt",
        }
    ]


def test_retrigger_after_own_write_is_noop(fake_monday):
    client.post("/monday/split-name", json=BODY, headers=auth())
    client.post("/monday/split-name", json=BODY, headers=auth())  # fired by our own write
    assert len(fake_monday["mutations"]) == 1


def test_short_name_does_not_write(fake_monday):
    fake_monday["text_mkt92ar9"] = "Müller & Söhne GmbH"
    res = client.post("/monday/split-name", json=BODY, headers=auth())
    assert res.status_code == 200
    assert fake_monday["mutations"] == []


def test_rejects_bad_or_missing_jwt(fake_monday):
    assert client.post("/monday/split-name", json=BODY, headers=auth("wrong-signing-secret-0123456789abcdef")).status_code == 401
    assert client.post("/monday/split-name", json=BODY).status_code == 401
    assert fake_monday["calls"] == 0


def test_same_column_returns_monday_error(fake_monday, monkeypatch):
    monkeypatch.setenv("TARGET_COLUMN_ID", "text_mkt92ar9")
    res = client.post("/monday/split-name", json=BODY, headers=auth())
    assert res.status_code == 400
    assert res.json()["severityCode"] == 4000


def test_reads_secret_from_monday_code_when_env_var_missing(monkeypatch):
    from app import config

    async def fake_monday_code(key):
        return {"MONDAY_SIGNING_SECRET": "from-monday-code-secret-0123456789"}.get(key)

    monkeypatch.delenv("MONDAY_SIGNING_SECRET")
    monkeypatch.setattr(config, "_from_monday_code", fake_monday_code)
    monkeypatch.setattr(config, "_cache", {})
    res = client.post("/monday/split-name", json=BODY, headers=auth("wrong-signing-secret-0123456789abcdef"))
    assert res.status_code == 401  # secret was found, so it got as far as checking the signature


def test_accepts_legacy_inbound_field_values(fake_monday):
    body = {"payload": {"inboundFieldValues": {"boardId": {"value": 1}, "itemId": 42}}}
    res = client.post("/", json=body, headers=auth())
    assert res.status_code == 200
    assert res.json() == {"outputFields": {}}
    assert len(fake_monday["mutations"]) == 1


def test_column_ids_can_be_overridden(fake_monday, monkeypatch):
    fake_monday["text_other"] = LONG_NAME
    monkeypatch.setenv("SOURCE_COLUMN_ID", "text_other")
    assert client.post("/", json=BODY, headers=auth()).status_code == 200
    assert set(fake_monday["mutations"][0]) == {"text_other", "text_mksb1npw"}


def test_missing_column_config_returns_monday_error(fake_monday, monkeypatch):
    from app import config

    async def not_on_monday_code(key):
        return None

    monkeypatch.delenv("TARGET_COLUMN_ID")
    monkeypatch.setattr(config, "_from_monday_code", not_on_monday_code)
    res = client.post("/", json=BODY, headers=auth())
    assert res.status_code == 400
    assert res.json()["notificationErrorTitle"] == "Columns not configured"
    assert fake_monday["calls"] == 0


def test_board_id_falls_back_to_default(fake_monday, monkeypatch):
    monkeypatch.setenv("DEFAULT_BOARD_ID", "5100825258")
    body = {"payload": {"inputFields": {"itemId": 42}}}
    assert client.post("/", json=body, headers=auth()).status_code == 200
    assert len(fake_monday["mutations"]) == 1


def test_missing_column_returns_monday_error(fake_monday, monkeypatch):
    monkeypatch.setenv("TARGET_COLUMN_ID", "text_gone")
    res = client.post("/", json=BODY, headers=auth())
    assert res.status_code == 400
    assert res.json()["notificationErrorTitle"] == "Name split failed"
    assert "text_gone" in res.json()["notificationErrorDescription"]
    assert fake_monday["mutations"] == []


def test_missing_item_returns_monday_error(fake_monday):
    res = client.post("/", json={"payload": {"inputFields": {"boardId": 1}}}, headers=auth())
    assert res.status_code == 400
    assert res.json()["notificationErrorTitle"] == "Missing input"
    assert fake_monday["calls"] == 0

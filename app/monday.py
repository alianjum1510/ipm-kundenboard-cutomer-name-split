"""Thin async client for the two monday GraphQL calls this app needs: read and write."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from .config import get_secret, settings


class MondayApiError(Exception):
    pass


@dataclass(frozen=True)
class ColumnValue:
    id: str
    type: str
    text: str


async def _gql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    api_token = await get_secret("MONDAY_API_TOKEN", "MONDAY_API_KEY")
    if not api_token:
        raise MondayApiError("MONDAY_API_TOKEN is not set")
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            settings.api_url,
            json={"query": query, "variables": variables},
            headers={
                "Authorization": api_token,
                "API-Version": settings.api_version,
                "Content-Type": "application/json",
            },
        )
    body = res.json()
    if res.status_code >= 400 or body.get("errors") or body.get("error_message"):
        detail = body.get("errors") or body.get("error_message")
        raise MondayApiError(f"monday API error ({res.status_code}): {json.dumps(detail)}")
    return body["data"]


async def read_columns(
    item_id: int, source_id: str, target_id: str
) -> tuple[ColumnValue, ColumnValue]:
    """Reads the current text and type of both columns in one call."""
    col_ids = [c for c in (source_id, target_id) if c != "name"]
    data = await _gql(
        """
        query ($itemId: [ID!], $colIds: [String!]) {
          items(ids: $itemId) {
            name
            column_values(ids: $colIds) { id type text }
          }
        }
        """,
        {"itemId": [item_id], "colIds": col_ids},
    )

    items = data.get("items") or []
    if not items:
        raise MondayApiError(f"Item {item_id} not found")
    item = items[0]

    def get(col_id: str) -> ColumnValue:
        if col_id == "name":
            return ColumnValue("name", "name", item["name"] or "")
        for cv in item["column_values"]:
            if cv["id"] == col_id:
                return ColumnValue(cv["id"], cv["type"], cv["text"] or "")
        raise MondayApiError(f'Column "{col_id}" not found on item {item_id}')

    return get(source_id), get(target_id)


def _value_for(col_type: str, text: str) -> Any:
    if col_type in ("name", "text"):
        return text
    if col_type == "long_text":
        return {"text": text}
    raise MondayApiError(
        f'Unsupported column type "{col_type}". Use a Text, Long Text or the Name column.'
    )


async def write_parts(
    board_id: int, item_id: int, cols: list[ColumnValue]
) -> None:
    """Writes both parts in a single mutation so the item never sits half updated."""
    values = {c.id: _value_for(c.type, c.text) for c in cols}
    await _gql(
        """
        mutation ($boardId: ID!, $itemId: ID!, $values: JSON!) {
          change_multiple_column_values(board_id: $boardId, item_id: $itemId, column_values: $values) { id }
        }
        """,
        {"boardId": board_id, "itemId": item_id, "values": json.dumps(values, ensure_ascii=False)},
    )

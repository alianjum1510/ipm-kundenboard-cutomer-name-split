"""
kundenname_split: monday.com Automation Block (action) for:
  "Split Kundenname for {Item id} in {board id}"
added to e.g. "When an item is created" (form submissions create items).

Names in Kundenname (Teil 1) over MAX_NAME_LENGTH characters are cut and the
overflow goes to Kundenname (Teil 2).

Block input fields (Developer Center):
  itemId   required
  boardId  fallback: DEFAULT_BOARD_ID

Columns come from the SOURCE_COLUMN_ID / TARGET_COLUMN_ID env vars
(sourceColumnId / targetColumnId in the block input win, if a block sends them).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from .auth import monday_session
from .config import assert_configured, get_secret, settings
from .monday import ColumnValue, read_columns, write_parts
from .split import split_customer_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kundenname_split")

@asynccontextmanager
async def lifespan(_: FastAPI):
    await assert_configured()
    yield


app = FastAPI(title="kundenname_split", lifespan=lifespan)


def _input(fields: dict, key: str):
    """Field value, unwrapping the object form some block field types use ({"value": ...})."""
    value = fields.get(key)
    if isinstance(value, dict):
        value = next((value[k] for k in ("value", "id", key) if value.get(k) not in (None, "")), None)
    return None if value in (None, "") else value


def monday_error(title: str, description: str) -> JSONResponse:
    """monday's error format, so the failure shows in the automation's activity log."""
    return JSONResponse(
        status_code=400,
        content={
            "severityCode": 4000,
            "notificationErrorTitle": title,
            "notificationErrorDescription": description,
            "runtimeErrorDescription": description,
        },
    )


@app.get("/")
@app.get("/health")
async def health() -> dict:
    return {"ok": True}


async def _column_id(fields: dict, input_key: str, env_key: str) -> str | None:
    """Column id from the block input, then the env var."""
    col_id = _input(fields, input_key) or await get_secret(env_key)
    return str(col_id) if col_id else None


# "/" so the bare monday-code Version URL works as the Execution URL, like the other apps.
@app.post("/", dependencies=[Depends(monday_session)])
@app.post("/monday/split-name", dependencies=[Depends(monday_session)])
async def split_name(request: Request):
    body = await request.json()
    payload = body.get("payload") or {}
    # Automation blocks (monday workflows) send `inputFields`; the legacy sentence builder `inboundFieldValues`.
    fields = payload.get("inputFields") or payload.get("inboundFieldValues") or {}
    log.info("input fields: %s", fields)

    try:
        board_id = int(_input(fields, "boardId") or await get_secret("DEFAULT_BOARD_ID"))
        item_id = int(_input(fields, "itemId"))
    except (TypeError, ValueError):
        return monday_error("Missing input", f"Board and item are required. Got: {fields}")

    source_id = await _column_id(fields, "sourceColumnId", "SOURCE_COLUMN_ID")
    target_id = await _column_id(fields, "targetColumnId", "TARGET_COLUMN_ID")
    if not source_id or not target_id:
        return monday_error(
            "Columns not configured", "Set SOURCE_COLUMN_ID and TARGET_COLUMN_ID in the app's environment variables."
        )

    if source_id == target_id:
        return monday_error(
            "Same column selected", "SOURCE_COLUMN_ID and TARGET_COLUMN_ID must be different columns."
        )

    try:
        source, target = await read_columns(item_id, source_id, target_id)
        result = split_customer_name(source.text, max_length=settings.max_name_length)

        # Short enough: nothing to do. This is also what stops the loop, because our own
        # write to the source column fires the trigger again with a value <= the limit.
        if not result.was_split:
            return {"outputFields": {}}

        if target.text and target.text != result.part2:
            log.info('[item %s] Teil 2 "%s" replaced with overflow "%s"', item_id, target.text, result.part2)
        if settings.teil2_max_length and len(result.part2) > settings.teil2_max_length:
            log.warning(
                "[item %s] Teil 2 is %d chars, over the %d limit",
                item_id, len(result.part2), settings.teil2_max_length,
            )

        await write_parts(
            board_id,
            item_id,
            [
                ColumnValue(source.id, source.type, result.part1),
                ColumnValue(target.id, target.type, result.part2),
            ],
        )

        log.info(
            "[item %s] split %d chars into %d + %d",
            item_id, len(source.text), len(result.part1), len(result.part2),
        )
        return {"outputFields": {}}
    except Exception as exc:  # noqa: BLE001 - surface any failure to monday's activity log
        log.exception("[item %s] split failed", item_id)
        return monday_error("Name split failed", str(exc))

"""Bounded JSON or starter-kit JSON/CSV uploads; filenames are never used as paths."""

import csv
import io
import json

from fastapi import HTTPException, Request
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from backend.loader import HISTORY_COLUMNS, _unique_object
from backend.schemas import UploadBatch


MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def parse_history(content: bytes) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
    if (reader.fieldnames is None or len(reader.fieldnames) != len(HISTORY_COLUMNS)
            or set(reader.fieldnames) != set(HISTORY_COLUMNS)):
        raise ValueError(f"activity_history.csv: expected columns {', '.join(HISTORY_COLUMNS)}")
    rows = []
    for line, row in enumerate(reader, start=2):
        if None in row or None in row.values():
            raise ValueError(f"activity_history.csv:{line}: wrong number of columns")
        for key in ("completion_pct", "score", "feedback_rating"):
            try:
                row[key] = None if row[key] == "" and key != "completion_pct" else int(row[key])
            except ValueError as exc:
                raise ValueError(f"activity_history.csv:{line}.{key}: expected an integer") from exc
        row["due_date"] = row["due_date"] or None
        rows.append(row)
    return rows


async def read_upload(request: Request) -> UploadBatch:
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Upload exceeds 2 MiB")
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    try:
        if media_type == "application/json":
            payload = json.loads(content, object_pairs_hook=_unique_object)
        elif media_type == "multipart/form-data":
            async def stream():
                yield bytes(content)

            form = await MultiPartParser(request.headers, stream(), max_files=2, max_fields=0).parse()
            try:
                items = form.multi_items()
                if (not items or len(set(form)) != len(items)
                        or set(form) - {"employees_file", "history_file"}
                        or any(not isinstance(value, UploadFile) for _, value in items)):
                    raise ValueError("Expected employees_file (JSON) and/or history_file (CSV), once each")
                payload = {}
                if "employees_file" in form:
                    payload = json.loads(await form["employees_file"].read(), object_pairs_hook=_unique_object)
                    if not isinstance(payload, dict) or set(payload) - {"meta", "employees"}:
                        raise ValueError("employees_file must contain the dataset {meta, employees} wrapper")
                if "history_file" in form:
                    payload["activity_history"] = parse_history(await form["history_file"].read())
            finally:
                await form.close()
        else:
            raise HTTPException(415, "Use application/json or multipart/form-data")
        return UploadBatch.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False, include_input=False)) from exc
    except (ValueError, UnicodeError, csv.Error, MultiPartException) as exc:
        raise HTTPException(422, str(exc)) from exc

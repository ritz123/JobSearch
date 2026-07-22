"""Build Excel (.xlsx) exports for filtered jobs."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
from openpyxl.styles import Font

URL_COLUMNS = ("Job URL", "Company URL")
_LINK_FONT = Font(color="0563C1", underline="single")


def _is_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return text.startswith("http://") or text.startswith("https://")


def apply_url_hyperlinks(worksheet, url_columns: tuple[str, ...] = URL_COLUMNS) -> None:
    """Turn http(s) URL cells into clickable Excel hyperlinks."""
    headers = [cell.value for cell in worksheet[1]]
    col_indexes = [headers.index(name) + 1 for name in url_columns if name in headers]
    if not col_indexes:
        return

    for row in range(2, worksheet.max_row + 1):
        for col in col_indexes:
            cell = worksheet.cell(row=row, column=col)
            if not _is_http_url(cell.value):
                continue
            url = str(cell.value).strip()
            cell.hyperlink = url
            cell.font = _LINK_FONT


def build_jobs_xlsx(records: list[dict]) -> bytes:
    """Return an .xlsx workbook (bytes) with clickable Job/Company URL columns."""
    df = pd.DataFrame.from_records(records)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        sheet = "Jobs"
        df.to_excel(writer, index=False, sheet_name=sheet)
        apply_url_hyperlinks(writer.sheets[sheet])
    return buf.getvalue()

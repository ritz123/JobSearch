"""Job board source adapters (Apify actors → shared job shape)."""

from __future__ import annotations

from typing import Any, Protocol


class SourceAdapter(Protocol):
    name: str
    actor_id: str

    def build_input(self, args: Any) -> dict: ...
    def normalize_items(self, items: list[dict]) -> list[dict]: ...


def get_adapter(source: str) -> SourceAdapter:
    from sources.indeed import IndeedSource
    from sources.linkedin import LinkedInSource
    from sources.naukri import NaukriSource

    adapters = {
        LinkedInSource.name: LinkedInSource(),
        NaukriSource.name: NaukriSource(),
        IndeedSource.name: IndeedSource(),
    }
    try:
        return adapters[source]
    except KeyError as exc:
        raise ValueError(f"Unknown source: {source!r}. Choose from: {', '.join(adapters)}") from exc

"""Asset-class plugin interface and registry.

A plugin owns everything that depends on how a class of security pays interest: its own
screens, the documents that define its terms (sources + extraction spec), its bond math, and
the narrative of a finding. Shared screens (null vs zero, frequency contradiction, cash
reconciliation, vendor disagreement) run on every security regardless of plugin.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

from termscheck.core.findings import FindingDraft
from termscheck.core.records import LedgerEntry, Position, SecurityRecord
from termscheck.extraction.spec import ExtractionSpec


@runtime_checkable
class AssetClassPlugin(Protocol):
    key: str
    label: str
    math_version: str                        # recorded on every computation
    term_fields: frozenset[str]              # reference-data fields that apply to this asset class
    screens: tuple[Any, ...]                 # plugin-specific Screen objects
    extraction: ExtractionSpec

    def terms_to_json(self, terms: Any) -> dict[str, Any]: ...

    def terms_from_json(self, data: dict[str, Any]) -> Any: ...

    def unsupported_reason(self, record: SecurityRecord, terms: Any) -> str | None:
        """Why this security cannot be computed by this plugin (None if supported). A finding is
        refused with this reason rather than produced from math that does not apply."""
        ...

    def build_finding(self, record: SecurityRecord, positions: list[Position], terms: Any, as_of: date, *,
                      citations: dict[str, dict] | None = None, rules: list[str] | None = None,
                      ledger: list[LedgerEntry] | None = None, context: dict[str, Any] | None = None
                      ) -> FindingDraft: ...


_REGISTRY: dict[str, AssetClassPlugin] = {}


def register(plugin: AssetClassPlugin) -> AssetClassPlugin:
    _REGISTRY[plugin.key] = plugin
    return plugin


def get_plugin(key: str) -> AssetClassPlugin:
    _load_builtin()
    try:
        return _REGISTRY[key]
    except KeyError:
        raise KeyError(f"no asset-class plugin {key!r}; registered: {sorted(_REGISTRY)}") from None


def all_plugins() -> dict[str, AssetClassPlugin]:
    _load_builtin()
    return dict(_REGISTRY)


def _load_builtin() -> None:
    if _REGISTRY:
        return
    import termscheck.plugins  # noqa: F401  (registers built-in plugins)

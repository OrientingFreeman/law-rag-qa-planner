from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class RetrievalConfig:
    lexical_weight: float = 0.55
    semantic_weight: float = 0.45
    top_k: int = 5


@dataclass(slots=True)
class DomainConfig:
    domain_id: str
    display_name: str
    laws: list[str] = field(default_factory=list)
    aliases: dict[str, list[str]] = field(default_factory=dict)
    query_rules: list[dict[str, object]] = field(default_factory=list)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)

    @classmethod
    def load(cls, path: str | Path) -> "DomainConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return cls(
            domain_id=raw["domain_id"],
            display_name=raw["display_name"],
            laws=raw.get("laws", []),
            aliases=raw.get("aliases", {}),
            query_rules=raw.get("query_rules", []),
            retrieval=RetrievalConfig(**raw.get("retrieval", {})),
        )


class DomainRegistry:
    def __init__(self, root: str | Path = "domains") -> None:
        self.root = Path(root)
        self._configs: dict[str, DomainConfig] = {}

    def load_all(self) -> "DomainRegistry":
        self._configs.clear()
        if not self.root.exists():
            return self
        for path in self.root.glob("*/domain.json"):
            config = DomainConfig.load(path)
            self._configs[config.domain_id] = config
        return self

    def get(self, domain_id: str | None) -> DomainConfig | None:
        if not domain_id or domain_id == "all":
            return None
        if not self._configs:
            self.load_all()
        return self._configs.get(domain_id)

    def list(self) -> list[DomainConfig]:
        if not self._configs:
            self.load_all()
        return sorted(self._configs.values(), key=lambda config: config.domain_id)

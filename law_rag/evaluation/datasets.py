from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path) -> str:
    """Hash JSON by semantic content so formatting and line endings do not matter."""
    resolved = Path(path)
    if resolved.suffix.lower() == ".json":
        payload = json.loads(resolved.read_text(encoding="utf-8-sig"))
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_id: str
    dataset_version: str
    ground_truth_version: str
    schema_version: str
    case_count: int
    content_sha256: str
    status: str
    created_at: str
    released_at: str | None
    review_policy: str
    approved_case_count: int
    source_snapshot_id: str
    parent_dataset_version: str | None = None
    change_summary: str = ""

    @classmethod
    def load(cls, path: str | Path) -> "DatasetManifest":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))

    def verify(self, dataset_path: str | Path, *, actual_case_count: int) -> list[str]:
        errors: list[str] = []
        if self.content_sha256 != sha256_file(dataset_path):
            errors.append("dataset_checksum_mismatch")
        if self.case_count != actual_case_count:
            errors.append("dataset_case_count_mismatch")
        if self.approved_case_count > self.case_count:
            errors.append("approved_case_count_exceeds_total")
        if self.status == "released" and self.approved_case_count != self.case_count:
            errors.append("released_dataset_contains_unapproved_cases")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def manifest_path_for(dataset_path: str | Path) -> Path:
    path = Path(dataset_path)
    return path.with_name(f"{path.stem}.manifest.json")


def load_dataset_manifest(dataset_path: str | Path) -> DatasetManifest | None:
    path = manifest_path_for(dataset_path)
    return DatasetManifest.load(path) if path.exists() else None


def dataset_snapshot(dataset_path: str | Path, *, case_count: int) -> dict[str, Any]:
    manifest = load_dataset_manifest(dataset_path)
    if manifest:
        errors = manifest.verify(dataset_path, actual_case_count=case_count)
        if errors:
            raise ValueError(f"invalid dataset manifest: {', '.join(errors)}")
        return manifest.to_dict()
    return {
        "dataset_id": Path(dataset_path).stem,
        "dataset_version": "unversioned",
        "ground_truth_version": "unversioned",
        "case_count": case_count,
        "content_sha256": sha256_file(dataset_path),
        "status": "unmanaged",
    }

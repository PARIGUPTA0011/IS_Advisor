"""
Single source of truth for standard metadata. Loads IS_Standards_Data/standards.jsonl
once and hydrates a StandardRecord by kys_id. This is what turns a bare
(kys_id, score) from any retriever implementation into full evidence.
"""

import json
from pathlib import Path
from typing import Optional

from rag.schemas import StandardRecord

DEFAULT_JSONL_PATH = (
    Path(__file__).resolve().parent.parent / "IS_Standards_Data" / "standards.jsonl"
)


def _record_from_json(rec: dict) -> StandardRecord:
    return StandardRecord(
        kys_id=int(rec["kys_id"]),
        is_number=rec.get("is_number") or "",
        title=rec.get("title") or "",
        status=rec.get("status") or None,
        aspect=rec.get("aspect") or None,
        department=rec.get("department") or None,
        committee=rec.get("committee") or None,
        group=rec.get("group") or None,
        sub_group=rec.get("sub_group") or None,
        sub_sub_group=rec.get("sub_sub_group") or None,
        mandatory_cert=rec.get("mandatory_cert") if isinstance(rec.get("mandatory_cert"), bool) else None,
        certification=rec.get("certification") or None,
        qco_status=rec.get("qco_status") or None,
        qco_date=rec.get("qco_date") or None,
        hs_codes=rec.get("hs_codes") or None,
        ministries=rec.get("ministries") or None,
        replaced_by_id=int(rec["replaced_by_id"]) if rec.get("replaced_by_id") not in (None, "") else None,
        replaced_by_is=rec.get("replaced_by_is") or None,
        revisions=str(rec["revisions"]) if rec.get("revisions") not in (None, "") else None,
        amendments_n=str(rec["amendments_n"]) if rec.get("amendments_n") not in (None, "") else None,
        reaffirmed_year=str(rec["reaffirmed_year"]) if rec.get("reaffirmed_year") not in (None, "") else None,
    )


class MetadataStore:
    def __init__(self, jsonl_path: Path = DEFAULT_JSONL_PATH):
        self._by_id: dict[int, StandardRecord] = {}
        self._by_is_number: dict[str, StandardRecord] = {}
        self._load(jsonl_path)

    def _load(self, jsonl_path: Path) -> None:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                raw = json.loads(line)
                record = _record_from_json(raw)
                self._by_id[record.kys_id] = record
                if record.is_number:
                    self._by_is_number[record.is_number] = record

    def __len__(self) -> int:
        return len(self._by_id)

    def get(self, kys_id: int) -> Optional[StandardRecord]:
        return self._by_id.get(kys_id)

    def get_by_is_number(self, is_number: str) -> Optional[StandardRecord]:
        return self._by_is_number.get(is_number)

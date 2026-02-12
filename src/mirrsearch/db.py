from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass(frozen=True)
class DBLayer:
    """
    Dummy DB layer that returns static data.
    """

    def _items(self) -> List[Dict[str, Any]]:
        return [
            {
                "docket_id": "CMS-2025-0240",
                "title": "CY 2026 Changes to the End-Stage Renal Disease (ESRD) Prospective Payment System and Quality Incentive Program. CMS1830-P Display",
                "cfrPart": "42 CFR Parts 413 and 512",
                "agency_id": "CMS",
                "document_type": "Proposed Rule",
            },
            {
                "docket_id": "CMS-2025-0240",
                "title": "Medicare Program: End-Stage Renal Disease Prospective Payment System, Payment for Renal Dialysis Services Furnished to Individuals with Acute Kidney Injury, End-Stage Renal Disease Quality Incentive Program, and End-Stage Renal Disease Treatment Choices Model",
                "cfrPart": "42 CFR Parts 413 and 512",
                "agency_id": "CMS",
                "document_type": "Proposed Rule",
            }
        ]

    def search(self, query: str) -> List[Dict[str, Any]]:
        # Query that matches title or docket_id in the dummy data and returns them
        q = query.lower().strip()
        return [
            item for item in self._items()
            if q in item["title"].lower() or q in item["docket_id"].lower()
        ]

def get_db() -> DBLayer:
    return DBLayer()

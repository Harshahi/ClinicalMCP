from __future__ import annotations

import os
from typing import Any

import httpx


class ClinicalTrialsClient:
    """Thin client for the ClinicalTrials.gov public API."""

    BASE_URL = "https://clinicaltrials.gov/api"

    def __init__(self, api_key: str | None = None, timeout: float = 20.0) -> None:
        self.api_key = api_key or os.getenv("CLINICALTRIALS_API_KEY")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def search_by_condition(
        self,
        condition: str,
        max_results: int = 5,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search ClinicalTrials.gov by condition or short phrase."""
        if not condition or not condition.strip():
            raise ValueError("condition is required")

        field_list = fields or [
            "NCTId",
            "BriefTitle",
            "Condition",
            "OverallStatus",
            "StudyType",
            "PrimaryCompletionDate",
            "BriefSummary",
        ]

        params = {
            "expr": f'AREA[ConditionSearch] "{condition.strip()}"',
            "fields": ",".join(field_list),
            "min_rnk": 1,
            "max_rnk": max(1, min(25, max_results)),
            "fmt": "json",
        }

        response = httpx.get(
            f"{self.BASE_URL}/query/study_fields",
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()

        payload = response.json()
        studies = payload.get("StudyFieldsResponse", {}).get("StudyFields", [])
        results: list[dict[str, Any]] = []

        for study in studies:
            values: dict[str, Any] = {}
            for item in study.get("StudyFields", []):
                key = item.get("Field")
                if key:
                    values[key] = item.get("FieldValue")
            results.append(
                {
                    "nct_id": values.get("NCTId"),
                    "brief_title": values.get("BriefTitle"),
                    "condition": values.get("Condition"),
                    "overall_status": values.get("OverallStatus"),
                    "study_type": values.get("StudyType"),
                    "primary_completion_date": values.get("PrimaryCompletionDate"),
                    "brief_summary": values.get("BriefSummary"),
                }
            )

        return results

    def get_study(self, nct_id: str) -> dict[str, Any]:
        """Fetch one study by NCT ID."""
        if not nct_id:
            raise ValueError("nct_id is required")

        params = {
            "expr": f'NCTId="{nct_id}"',
            "fields": "NCTId,BriefTitle,Condition,OverallStatus,PrimaryCompletionDate,BriefSummary",
            "min_rnk": 1,
            "max_rnk": 1,
            "fmt": "json",
        }

        response = httpx.get(
            f"{self.BASE_URL}/query/study_fields",
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        studies = payload.get("StudyFieldsResponse", {}).get("StudyFields", [])
        if not studies:
            return {}

        first = studies[0].get("StudyFields", [])
        values: dict[str, Any] = {}
        for item in first:
            key = item.get("Field")
            if key:
                values[key] = item.get("FieldValue")

        return {
            "nct_id": values.get("NCTId"),
            "brief_title": values.get("BriefTitle"),
            "condition": values.get("Condition"),
            "overall_status": values.get("OverallStatus"),
            "primary_completion_date": values.get("PrimaryCompletionDate"),
            "brief_summary": values.get("BriefSummary"),
        }

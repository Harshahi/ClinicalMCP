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

    @staticmethod
    def _normalize_study(study: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(study, dict):
            return {
                "nct_id": None,
                "brief_title": None,
                "condition": None,
                "overall_status": None,
                "study_type": None,
                "primary_completion_date": None,
                "brief_summary": None,
            }

        if "StudyFields" in study:
            values: dict[str, Any] = {}
            for item in study.get("StudyFields", []):
                key = item.get("Field")
                if key:
                    values[key] = item.get("FieldValue")
            return {
                "nct_id": values.get("NCTId"),
                "brief_title": values.get("BriefTitle"),
                "condition": values.get("Condition"),
                "overall_status": values.get("OverallStatus"),
                "study_type": values.get("StudyType"),
                "primary_completion_date": values.get("PrimaryCompletionDate"),
                "brief_summary": values.get("BriefSummary"),
            }

        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        conditions_module = protocol.get("conditionsModule", {})
        status_module = protocol.get("statusModule", {})
        design_module = protocol.get("designModule", {})
        description_module = protocol.get("descriptionModule", {})

        conditions = conditions_module.get("conditions", [])
        condition_text = next(
            (item.get("condition") for item in conditions if isinstance(item, dict) and item.get("condition")),
            None,
        )

        return {
            "nct_id": identification.get("nctId"),
            "brief_title": identification.get("briefTitle"),
            "condition": condition_text,
            "overall_status": status_module.get("overallStatus"),
            "study_type": design_module.get("studyType"),
            "primary_completion_date": status_module.get("primaryCompletionDate"),
            "brief_summary": description_module.get("briefSummary"),
        }

    def search_by_condition(
        self,
        condition: str,
        max_results: int = 5,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search ClinicalTrials.gov by condition or short phrase."""
        if not condition or not condition.strip():
            raise ValueError("condition is required")

        query = condition.strip()
        params = {
            "query.term": query,
            "pageSize": max(1, min(25, max_results)),
            "format": "json",
        }

        response = httpx.get(
            f"{self.BASE_URL}/v2/studies",
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()

        payload = response.json()
        studies = payload.get("studies", [])
        if not studies and "StudyFieldsResponse" in payload:
            studies = payload.get("StudyFieldsResponse", {}).get("StudyFields", [])
        return [self._normalize_study(study) for study in studies[: max(1, min(25, max_results))]]

    def get_study(self, nct_id: str) -> dict[str, Any]:
        """Fetch one study by NCT ID."""
        if not nct_id:
            raise ValueError("nct_id is required")

        response = httpx.get(
            f"{self.BASE_URL}/v2/studies/{nct_id}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload:
            return {}

        if "StudyFieldsResponse" in payload:
            studies = payload.get("StudyFieldsResponse", {}).get("StudyFields", [])
            if not studies:
                return {}
            return self._normalize_study(studies[0])

        return self._normalize_study(payload)

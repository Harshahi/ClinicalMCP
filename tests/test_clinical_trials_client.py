from __future__ import annotations

from unittest.mock import patch

from mcp_clinical.api import ClinicalTrialsClient


def test_search_by_condition_builds_expected_query() -> None:
    client = ClinicalTrialsClient(timeout=5.0)

    with patch("mcp_clinical.api.httpx.get") as mock_get:
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "StudyFieldsResponse": {
                "StudyFields": [
                    {
                        "StudyFields": [
                            {"Field": "NCTId", "FieldValue": "NCT000001"},
                            {"Field": "BriefTitle", "FieldValue": "Sample trial"},
                            {"Field": "Condition", "FieldValue": "Diabetes"},
                        ]
                    }
                ]
            }
        }

        result = client.search_by_condition("diabetes", max_results=3)

    assert result[0]["nct_id"] == "NCT000001"
    assert result[0]["brief_title"] == "Sample trial"
    assert result[0]["condition"] == "Diabetes"
    assert mock_get.call_args.kwargs["params"]["max_rnk"] == 3


def test_get_study_returns_empty_when_no_matches() -> None:
    client = ClinicalTrialsClient(timeout=5.0)

    with patch("mcp_clinical.api.httpx.get") as mock_get:
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {"StudyFieldsResponse": {"StudyFields": []}}

        result = client.get_study("NCT000001")

    assert result == {}

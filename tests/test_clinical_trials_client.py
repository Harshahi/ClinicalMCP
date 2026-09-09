from __future__ import annotations

import os
from unittest.mock import patch

from mcp_clinical.api import ClinicalTrialsClient
from mcp_clinical.server import get_company_price


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
    assert mock_get.call_args.kwargs["params"]["pageSize"] == 3


def test_get_study_returns_empty_when_no_matches() -> None:
    client = ClinicalTrialsClient(timeout=5.0)

    with patch("mcp_clinical.api.httpx.get") as mock_get:
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {"StudyFieldsResponse": {"StudyFields": []}}

        result = client.get_study("NCT000001")

    assert result == {}


def test_search_by_condition_handles_v2_api_payload() -> None:
    client = ClinicalTrialsClient(timeout=5.0)

    with patch("mcp_clinical.api.httpx.get") as mock_get:
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT000001",
                            "briefTitle": "Sample trial",
                        },
                        "conditionsModule": {
                            "conditions": [{"condition": "Diabetes"}],
                        },
                        "statusModule": {"overallStatus": "Active, not recruiting"},
                        "designModule": {"studyType": "Interventional"},
                        "descriptionModule": {"briefSummary": "A short summary."},
                    }
                }
            ]
        }

        result = client.search_by_condition("diabetes", max_results=3)

    assert result[0]["nct_id"] == "NCT000001"
    assert result[0]["brief_title"] == "Sample trial"
    assert result[0]["condition"] == "Diabetes"
    assert result[0]["overall_status"] == "Active, not recruiting"
    assert "studies" in mock_get.call_args[0][0]


def test_get_company_price_uses_finnhub_when_api_key_is_set() -> None:
    with patch.dict(os.environ, {"FINNHUB_API_KEY": "demo-token"}, clear=False):
        with patch("mcp_clinical.server.httpx.Client") as mock_client:
            mock_response = mock_client.return_value.__enter__.return_value.get.return_value
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {"c": 123.45, "pc": 120.0}

            result = get_company_price("AAPL", range_name="1d")

    assert result["ticker"] == "AAPL"
    assert result["price"] == 123.45
    assert result["previous_close"] == 120.0
    assert result["source"] == "Finnhub"
    assert "finnhub.io" in mock_client.return_value.__enter__.return_value.get.call_args[0][0]


def test_get_company_price_falls_back_to_twelve_data_without_api_key() -> None:
    with patch.dict(os.environ, {"FINNHUB_API_KEY": ""}, clear=False):
        with patch("mcp_clinical.server.httpx.Client") as mock_client:
            mock_response = mock_client.return_value.__enter__.return_value.get.return_value
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {"price": "123.45"}

            result = get_company_price("AAPL", range_name="1d")

    assert result["ticker"] == "AAPL"
    assert result["price"] == 123.45
    assert result["source"] == "Twelve Data"
    assert "api.twelvedata.com" in mock_client.return_value.__enter__.return_value.get.call_args[0][0]

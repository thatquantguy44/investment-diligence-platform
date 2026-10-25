import pytest

from diligence_pipelines.alerts import build_slack_refresh_alert


def test_build_slack_refresh_alert_has_no_delivery_side_effects():
    payload = build_slack_refresh_alert(
        {
            "status": "blocked",
            "refresh_id": "refresh-2026-10-25",
            "reason": "Catalog artifact requires analyst review.",
            "download_url": "https://api.uspto.gov/example.tsv.zip",
        },
        environment="production",
    )

    assert payload["text"] == "USPTO approved refresh blocked: refresh-2026-10-25"
    assert payload["blocks"][1]["fields"][0]["text"] == "*Environment*\nproduction"
    assert "Catalog artifact requires analyst review." in payload["blocks"][2]["text"]["text"]


def test_build_slack_refresh_alert_rejects_non_alert_statuses():
    with pytest.raises(ValueError, match="blocked or failed"):
        build_slack_refresh_alert({"status": "prepared"}, environment="production")

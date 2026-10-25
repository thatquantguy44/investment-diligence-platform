"""Alert payload builders for operator-controlled delivery channels.

The Slack webhook configuration is deliberately not dispatched from this
module. Keeping payload construction separate lets operators review message
content and delivery policy before any pipeline can notify an external system.
"""

from __future__ import annotations

from typing import Any


def build_slack_refresh_alert(report: dict[str, Any], *, environment: str) -> dict[str, Any]:
    """Build a Slack Incoming Webhook payload for a blocked or failed refresh.

    This function performs no network I/O. A future runtime integration must
    explicitly choose which refresh outcomes notify Slack, retry behavior, and
    ownership of the configured webhook.
    """
    status = str(report.get("status", "unknown"))
    if status not in {"blocked", "failed"}:
        raise ValueError("Slack refresh alerts are limited to blocked or failed reports")

    refresh_id = str(report.get("refresh_id", "unknown refresh"))
    reason = str(report.get("reason", "No reason was recorded."))
    artifact = str(report.get("download_url", report.get("artifact_path", "Not recorded")))
    title = f"USPTO approved refresh {status}: {refresh_id}"
    return {
        "text": title,
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Environment*\n{environment}"},
                    {"type": "mrkdwn", "text": f"*Status*\n{status}"},
                    {"type": "mrkdwn", "text": f"*Artifact*\n{artifact}"},
                ],
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Reason*\n{reason}"}},
        ],
    }

from __future__ import annotations

from uuid import UUID

from .api_client import ZubePredictAPIError, ZubePredictClient
from .report_delivery import render_report_data
from .telegram_security import TelegramAccessDenied


def link_command(raw_args: str) -> str:
    """Redeem one dashboard code without sending it through the LLM."""

    code = raw_args.strip()
    if len(code) != 8 or not code.isascii() or not code.isdigit():
        return "Use /zlink followed by the eight-digit code from your dashboard."
    try:
        response = ZubePredictClient().request(
            "POST", "/hermes/account-links/telegram/redeem", payload={"code": code}
        )
        if isinstance(response, dict) and response.get("status") == "linked":
            return "Telegram is now connected to your ZubePredict account."
        return "The linking code could not be used. Request a new code from the dashboard."
    except (ValueError, ZubePredictAPIError):
        return "The linking code is invalid, expired, or already used."
    except (KeyError, TelegramAccessDenied):
        return "This Telegram account is not linked or authorised."
    except Exception:
        return "ZubePredict is temporarily unavailable. Please try again later."


def report_command(raw_args: str) -> str:
    """Return an exact evidence-report URL directly through the gateway command path."""

    if raw_args.strip():
        return "Use /zreport without any extra text."
    try:
        client = ZubePredictClient()
        channel = client.request("GET", "/hermes/channel/state", retry_safe=True)
        state = channel.get("state") if isinstance(channel, dict) else None
        experiment_id = state.get("active_experiment_id") if isinstance(state, dict) else None
        if not experiment_id:
            return "No active experiment is selected. Select an owned experiment first."
        safe_experiment_id = UUID(str(experiment_id))
        report = client.request(
            "GET",
            f"/hermes/experiments/{safe_experiment_id}/reports/evidence",
            retry_safe=True,
        )
        rendered = render_report_data(report)
        if rendered is None:
            return "The report reference is unavailable. Please try again."
        return rendered
    except (ValueError, ZubePredictAPIError):
        return "The report reference is unavailable. Please try again."
    except (KeyError, TelegramAccessDenied):
        return "This Telegram account is not linked or authorised."
    except Exception:
        return "ZubePredict is temporarily unavailable. Your experiment has not been restarted."

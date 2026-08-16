"""Fail-safe Stage 17 private-artifact retention executor.

Dry-run is the default. Execution requires an exact confirmation phrase.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from typing import Any

from supabase import create_client
from zubepredict_core.shared.config import get_settings

CONFIRMATION = "DELETE-EXPIRED-PRIVATE-ARTIFACTS"


def _expired(client: Any, table: str, now: datetime) -> list[dict[str, Any]]:
    response = (
        client.table(table)
        .select("id,owner_id,storage_path")
        .eq("retention_status", "active")
        .lt("retention_expires_at", now.isoformat())
        .execute()
    )
    return [dict(item) for item in (response.data or [])]


def _audit(client: Any, row: dict[str, Any], table: str) -> None:
    resource_type = "dataset" if table == "datasets" else "report"
    client.table("audit_logs").insert(
        {
            "owner_id": row["owner_id"],
            "action": f"{resource_type}.retention_expired",
            "resource_type": resource_type,
            "resource_id": row["id"],
            "metadata": {"policy": "automatic_retention", "storage_deleted": True},
        }
    ).execute()


def execute_sweep(client: Any, *, datasets_bucket: str, artifacts_bucket: str) -> dict[str, int]:
    now = datetime.now(UTC)
    counts = {"datasets": 0, "reports": 0}
    for table, bucket_name in (("datasets", datasets_bucket), ("reports", artifacts_bucket)):
        for row in _expired(client, table, now):
            client.table(table).update({"retention_status": "deletion_pending"}).eq(
                "id", row["id"]
            ).eq("owner_id", row["owner_id"]).eq("retention_status", "active").execute()
            try:
                client.storage.from_(bucket_name).remove([row["storage_path"]])
                changes: dict[str, Any] = {"retention_status": "expired"}
                if table == "datasets":
                    changes.update(profile={}, original_filename="expired-dataset")
                else:
                    changes["deleted_at"] = now.isoformat()
                client.table(table).update(changes).eq("id", row["id"]).eq(
                    "owner_id", row["owner_id"]
                ).execute()
                _audit(client, row, table)
                counts[table] += 1
            except Exception:
                client.table(table).update({"retention_status": "active"}).eq(
                    "id", row["id"]
                ).eq("owner_id", row["owner_id"]).execute()
                raise
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    settings = get_settings()
    secret = settings.supabase_service_role_key.get_secret_value()
    if not settings.supabase_url or not secret:
        raise SystemExit("Retention preflight failed: Supabase server credentials are missing.")
    client = create_client(settings.supabase_url, secret)
    now = datetime.now(UTC)
    planned = {
        "datasets": len(_expired(client, "datasets", now)),
        "reports": len(_expired(client, "reports", now)),
    }
    if not args.execute:
        print(f"Dry run only: {planned['datasets']} dataset(s), {planned['reports']} report(s).")
        return 0
    if args.confirm != CONFIRMATION:
        raise SystemExit("Execution refused: the exact confirmation phrase is required.")
    completed = execute_sweep(
        client,
        datasets_bucket=settings.supabase_datasets_bucket,
        artifacts_bucket=settings.supabase_artifacts_bucket,
    )
    print(
        f"Retention completed: {completed['datasets']} dataset(s), "
        f"{completed['reports']} report(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

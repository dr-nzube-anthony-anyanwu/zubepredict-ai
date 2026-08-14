from fastapi.testclient import TestClient
from zubepredict_api.main import app
from zubepredict_api.routes import analysis as analysis_routes

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_versioned_health_alias() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_profile_rejects_unsupported_file_type() -> None:
    response = client.post(
        "/api/v1/analysis/profile",
        files={"file": ("dataset.txt", b"value\n1\n", "text/plain")},
    )

    assert response.status_code == 422
    assert "Unsupported file type" in response.json()["detail"]


def test_profile_rejects_empty_csv() -> None:
    response = client.post(
        "/api/v1/analysis/profile",
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    assert response.status_code == 422
    assert "dataset is empty" in response.json()["detail"]


def test_api_rejects_file_over_size_limit(monkeypatch) -> None:
    monkeypatch.setattr(analysis_routes.settings, "max_upload_mb", 1)
    response = client.post(
        "/api/v1/analysis/profile",
        files={"file": ("large.csv", b"x" * ((1024 * 1024) + 1), "text/csv")},
    )

    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]


def test_dataset_upload_intent_requires_authentication() -> None:
    response = client.post(
        "/api/v1/datasets/upload-intents",
        json={
            "project_id": "00000000-0000-0000-0000-000000000001",
            "filename": "dataset.csv",
            "content_type": "text/csv",
        },
    )

    assert response.status_code == 401
    assert "bearer" in response.json()["detail"].lower()


def test_task_override_requires_authentication() -> None:
    response = client.post(
        "/api/v1/decisions/experiments/00000000-0000-0000-0000-000000000001/override",
        json={
            "task_type": "binary_classification",
            "target_column": "churn",
            "rationale": "The user explicitly confirmed the target.",
            "confirmed_by_user": True,
        },
    )

    assert response.status_code == 401
    assert "bearer" in response.json()["detail"].lower()


def test_experiment_job_requires_authentication() -> None:
    response = client.post(
        "/api/v1/experiments/jobs",
        headers={"Idempotency-Key": "stage-seven-test"},
        json={
            "project_id": "00000000-0000-0000-0000-000000000001",
            "dataset_id": "00000000-0000-0000-0000-000000000002",
        },
    )

    assert response.status_code == 401
    assert "bearer" in response.json()["detail"].lower()


def test_quality_endpoint_returns_structured_blockers_and_warnings() -> None:
    csv = b"age,target,target_copy\n20,no,no\n30,yes,yes\n40,no,no\n50,yes,yes\n"

    response = client.post(
        "/api/v1/analysis/quality",
        files={"file": ("dataset.csv", csv, "text/csv")},
        data={"target_column": "target"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_train"] is False
    assert "exact_target_duplicate" in {finding["code"] for finding in payload["blocking_errors"]}
    assert len(payload["evidence_hash"]) == 64


def test_quality_endpoint_requires_exact_acknowledgement_for_forced_risk() -> None:
    rows = ["row_id,feature,target"] + [f"{index},{index % 7},{index % 2}" for index in range(30)]
    csv = ("\n".join(rows) + "\n").encode()

    blocked = client.post(
        "/api/v1/analysis/quality",
        files={"file": ("dataset.csv", csv, "text/csv")},
        data={"target_column": "target", "forced_features": "row_id"},
    )
    allowed = client.post(
        "/api/v1/analysis/quality",
        files={"file": ("dataset.csv", csv, "text/csv")},
        data={
            "target_column": "target",
            "forced_features": "row_id",
            "acknowledged_risks": "suspected_identifier:row_id",
        },
    )

    assert blocked.status_code == 200
    assert blocked.json()["can_train"] is False
    assert allowed.status_code == 200
    assert allowed.json()["can_train"] is True
    finding = next(
        item for item in allowed.json()["findings"] if item["id"] == "suspected_identifier:row_id"
    )
    assert finding["acknowledged"] is True


def test_quick_tournament_cannot_bypass_quality_blocker() -> None:
    rows = ["age,target,target_copy"] + [
        f"{20 + index},{index % 2},{index % 2}" for index in range(30)
    ]
    response = client.post(
        "/api/v1/analysis/quick-tournament",
        files={"file": ("dataset.csv", ("\n".join(rows) + "\n").encode(), "text/csv")},
        data={"target_column": "target"},
    )

    assert response.status_code == 422
    assert "exactly duplicates the target" in response.json()["detail"]


def test_quick_tournament_returns_stage6_validation_evidence(monkeypatch) -> None:
    monkeypatch.setattr(analysis_routes.settings, "max_candidate_models", 1)
    rows = ["age,signal,target"] + [
        f"{20 + index},{index % 7},{'yes' if index % 2 else 'no'}" for index in range(40)
    ]

    response = client.post(
        "/api/v1/analysis/quick-tournament",
        files={"file": ("dataset.csv", ("\n".join(rows) + "\n").encode(), "text/csv")},
        data={"target_column": "target"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["fitted_winner"] is True
    assert payload["validation_strategy"].startswith("5-fold shuffled StratifiedKFold")
    assert len(payload["out_of_fold_predictions"]) == 40
    assert payload["calibration"] is not None
    assert payload["threshold_analysis"] is not None
    assert len(payload["leaderboard"][0]["fold_scores"]) == 5

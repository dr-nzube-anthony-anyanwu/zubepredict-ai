import pandas as pd
import pytest
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.datasets import load_breast_cancer, load_diabetes
from zubepredict_core.data_engine.task_detector import detect_task
from zubepredict_core.ml_engine import tournament
from zubepredict_core.ml_engine.tournament import run_supervised_tournament


def test_classification_tournament_returns_winner() -> None:
    dataset = load_breast_cancer(as_frame=True)
    df = dataset.frame.head(180)
    decision = detect_task(df, "target")
    result = run_supervised_tournament(df, decision, max_models=2)
    assert result.winner
    assert len(result.leaderboard) == 2
    assert result.primary_metric == "average_precision"
    assert result.fitted_winner is True
    assert result.random_seed == 42
    assert result.software_versions["python"].startswith("3.11")
    assert len(result.out_of_fold_predictions) == len(df)
    assert result.calibration is not None
    assert result.threshold_analysis is not None
    assert {"average_precision", "roc_auc", "recall", "f1", "brier_score"} <= set(
        result.leaderboard[0].metrics
    )
    assert len(result.leaderboard[0].fold_scores) == 5
    assert len(result.leaderboard[0].metrics["average_precision"].fold_values) == 5
    assert result.leaderboard[0].hyperparameters


def test_regression_tournament_returns_winner() -> None:
    dataset = load_diabetes(as_frame=True)
    df = dataset.frame.head(180)
    decision = detect_task(df, "target")
    result = run_supervised_tournament(df, decision, max_models=2)
    assert result.winner
    assert result.primary_metric == "root_mean_squared_error"
    assert result.calibration is None
    assert result.threshold_analysis is None
    assert {"root_mean_squared_error", "mean_absolute_error", "r2"} == set(
        result.leaderboard[0].metrics
    )


def test_failed_candidate_is_isolated(monkeypatch) -> None:
    original_models = tournament._classification_models

    def models_with_failure(seed: int):
        return {
            "Baseline": original_models(seed)["Baseline"],
            "Broken candidate": lambda: object(),
        }

    monkeypatch.setattr(tournament, "_classification_models", models_with_failure)
    dataframe = pd.DataFrame(
        {
            "age": [20, 21, 22, 23, 24, 25, 26, 27],
            "target": ["no", "yes", "no", "yes", "no", "yes", "no", "yes"],
        }
    )
    decision = detect_task(dataframe, "target")

    result = run_supervised_tournament(dataframe, decision, max_models=2)

    assert result.winner == "Baseline"
    assert result.leaderboard[0].status == "completed"
    assert result.leaderboard[1].model_name == "Broken candidate"
    assert result.leaderboard[1].status == "failed"
    assert result.leaderboard[1].error


def test_tournament_blocks_exact_target_leakage() -> None:
    dataframe = pd.DataFrame(
        {
            "age": range(30),
            "target": ["no", "yes"] * 15,
            "leaked_outcome": ["no", "yes"] * 15,
        }
    )
    decision = detect_task(dataframe, "target")

    with pytest.raises(ValueError, match="exactly duplicates the target"):
        run_supervised_tournament(dataframe, decision, max_models=1)


def test_tournament_carries_quality_evidence_and_safe_exclusions() -> None:
    dataframe = pd.DataFrame(
        {
            "row_id": range(40),
            "age": range(20, 60),
            "target": ["no", "yes"] * 20,
        }
    )
    decision = detect_task(dataframe, "target")

    result = run_supervised_tournament(dataframe, decision, max_models=1)

    assert result.winner == "Baseline"
    assert result.quality_report is not None
    assert "row_id" in result.quality_report.suggested_exclusions
    assert len(result.quality_report.evidence_hash) == 64


def test_multiclass_tournament_uses_proper_metric_dictionary() -> None:
    dataframe = pd.DataFrame(
        {
            "feature_a": range(90),
            "feature_b": [index % 7 for index in range(90)],
            "target": ["low", "medium", "high"] * 30,
        }
    )
    decision = detect_task(dataframe, "target")

    result = run_supervised_tournament(dataframe, decision, max_models=1)

    assert result.primary_metric == "f1_macro"
    assert {"f1_macro", "balanced_accuracy", "roc_auc_ovr_macro", "log_loss"} == set(
        result.leaderboard[0].metrics
    )


def test_winner_is_saved_with_skops_only_after_selection(tmp_path) -> None:
    dataframe = pd.DataFrame(
        {
            "feature": range(40),
            "target": ["no", "yes"] * 20,
        }
    )
    decision = detect_task(dataframe, "target")
    artifact = tmp_path / "winner.skops"

    result = run_supervised_tournament(
        dataframe,
        decision,
        max_models=1,
        winner_artifact_path=artifact,
    )

    assert result.winner_artifact is not None
    assert result.winner_artifact.format == "skops"
    assert len(result.winner_artifact.sha256) == 64
    assert result.winner_artifact.size_bytes == artifact.stat().st_size
    assert result.winner_artifact.untrusted_types == ["numpy.dtype"]
    assert artifact.read_bytes()[:2] == b"PK"
    assert not list(tmp_path.glob("*.pkl"))
    assert not list(tmp_path.glob("*.joblib"))


def test_optional_advanced_models_are_guarded(monkeypatch) -> None:
    monkeypatch.setattr(tournament, "_has_module", lambda _module: False)

    classification = tournament._classification_models(42)
    regression = tournament._regression_models(42)

    for name in ("XGBoost", "LightGBM", "CatBoost"):
        assert name not in classification
        assert name not in regression


@pytest.mark.parametrize("advanced_name", ["XGBoost", "LightGBM", "CatBoost"])
def test_installed_advanced_candidate_completes_common_string_label_task(
    advanced_name, monkeypatch
) -> None:
    dataframe = pd.DataFrame(
        {
            "feature_a": range(60),
            "feature_b": [index % 7 for index in range(60)],
            "target": ["no", "yes"] * 30,
        }
    )
    decision = detect_task(dataframe, "target")
    factories = tournament._classification_models(42)
    if advanced_name not in factories:
        pytest.skip(f"{advanced_name} is an optional dependency")
    monkeypatch.setattr(
        tournament,
        "_classification_models",
        lambda _seed: {
            "Baseline": factories["Baseline"],
            advanced_name: factories[advanced_name],
        },
    )

    result = run_supervised_tournament(dataframe, decision, max_models=2)
    by_name = {score.model_name: score for score in result.leaderboard}

    assert by_name[advanced_name].status == "completed"
    assert len(by_name[advanced_name].fold_scores) == 5


class FailsOnThirdFit(ClassifierMixin, BaseEstimator):
    fit_calls = 0

    def fit(self, _features, target):
        type(self).fit_calls += 1
        if type(self).fit_calls == 3:
            raise RuntimeError("third fold failure")
        self.classes_ = pd.unique(target)
        return self

    def predict(self, features):
        return [self.classes_[0]] * len(features)

    def predict_proba(self, features):
        probability = 1 / len(self.classes_)
        return [[probability] * len(self.classes_) for _ in range(len(features))]


def test_partial_fold_scores_and_failure_stage_are_preserved(monkeypatch) -> None:
    original_models = tournament._classification_models
    FailsOnThirdFit.fit_calls = 0

    def models_with_partial_failure(seed: int):
        return {
            "Baseline": original_models(seed)["Baseline"],
            "Partially broken": FailsOnThirdFit,
        }

    monkeypatch.setattr(tournament, "_classification_models", models_with_partial_failure)
    dataframe = pd.DataFrame(
        {
            "feature": range(40),
            "target": ["no", "yes"] * 20,
        }
    )
    decision = detect_task(dataframe, "target")

    result = run_supervised_tournament(dataframe, decision, max_models=2)

    failed = next(score for score in result.leaderboard if score.model_name == "Partially broken")
    assert failed.status == "failed"
    assert failed.failure_stage == "cross_validation_fold_3"
    assert len(failed.fold_scores) == 2
    assert failed.error == "third fold failure"

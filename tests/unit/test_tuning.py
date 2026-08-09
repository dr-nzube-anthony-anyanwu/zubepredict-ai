from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from zubepredict_core.data_engine.task_detector import detect_task
from zubepredict_core.ml_engine.tournament import (
    TournamentCancelled,
    run_supervised_tournament,
)
from zubepredict_core.ml_engine.tuning import resolve_tuning_budget, run_optuna_tuning
from zubepredict_core.shared.schemas import ModelScore


def _score(name: str, value: float = 1.0) -> SimpleNamespace:
    return SimpleNamespace(
        score=ModelScore(
            model_name=name,
            primary_metric="root_mean_squared_error",
            mean_score=value,
            score_std=0,
            fit_seconds=0,
        )
    )


def test_budget_applies_user_experiment_and_dataset_limits() -> None:
    budget = resolve_tuning_budget(
        rows=25_000,
        requested_trials=50,
        requested_seconds=500,
        experiment_trial_limit=10,
        experiment_time_limit_seconds=120,
        user_trial_limit=7,
        user_time_limit_seconds=90,
        max_candidates=4,
    )

    assert budget.dataset_size_band == "large"
    assert budget.effective_max_trials == 3
    assert budget.effective_time_limit_seconds == 90
    assert budget.candidate_limit == 1
    assert len(budget.reduction_reasons) == 4


def test_optuna_trials_are_bounded_and_pruned_at_fold_boundaries() -> None:
    budget = resolve_tuning_budget(
        rows=100,
        requested_trials=2,
        requested_seconds=30,
        experiment_trial_limit=2,
        experiment_time_limit_seconds=30,
        user_trial_limit=4,
        user_time_limit_seconds=60,
        max_candidates=1,
    )

    def evaluate(name, factory, fold_progress):
        factory()
        value = 0.1 if name.endswith("1") else 0.9
        for fold in range(1, 4):
            fold_progress(fold, value)
        return _score(name, value)

    outcome = run_optuna_tuning(
        ordered_evaluations=[_score("Ridge Regression")],
        factories={"Ridge Regression": Ridge},
        evaluate=evaluate,
        direction="maximize",
        seed=42,
        budget=budget,
    )

    assert outcome.summary.total_trials == 2
    assert outcome.summary.completed_trials == 1
    assert outcome.summary.pruned_trials == 1
    assert outcome.summary.trials[1].last_reported_fold == 1
    assert outcome.evaluations[0].score.is_tuned is True
    assert outcome.evaluations[0].score.untuned_model_name == "Ridge Regression"


def test_tuning_honours_cancellation_before_a_trial() -> None:
    budget = resolve_tuning_budget(
        rows=100,
        requested_trials=2,
        requested_seconds=30,
        experiment_trial_limit=2,
        experiment_time_limit_seconds=30,
        user_trial_limit=2,
        user_time_limit_seconds=30,
        max_candidates=1,
    )

    with pytest.raises(TournamentCancelled):
        run_optuna_tuning(
            ordered_evaluations=[_score("Ridge Regression")],
            factories={"Ridge Regression": DummyRegressor},
            evaluate=lambda *_args: _score("unused"),
            direction="minimize",
            seed=42,
            budget=budget,
            cancellation_check=lambda: True,
        )


def test_tournament_keeps_untuned_results_and_is_deterministic() -> None:
    dataframe = pd.DataFrame(
        {
            "signal": range(80),
            "secondary": [index % 9 for index in range(80)],
            "target": [index * 0.4 + (index % 5) for index in range(80)],
        }
    )
    decision = detect_task(dataframe, "target")
    options = {
        "max_models": 2,
        "tuning_enabled": True,
        "tuning_trials": 3,
        "tuning_timeout_seconds": 30,
        "experiment_tuning_trial_limit": 3,
        "experiment_tuning_time_limit_seconds": 30,
        "user_tuning_trial_limit": 5,
        "user_tuning_time_limit_seconds": 60,
        "tuning_max_candidates": 1,
    }

    first = run_supervised_tournament(dataframe, decision, **options)
    second = run_supervised_tournament(dataframe, decision, **options)

    first_by_name = {score.model_name: score for score in first.leaderboard}
    second_by_name = {score.model_name: score for score in second.leaderboard}
    assert {"Baseline", "Ridge Regression", "Ridge Regression (Optuna tuned)"} == set(first_by_name)
    assert first_by_name["Baseline"].is_tuned is False
    assert first_by_name["Ridge Regression"].is_tuned is False
    assert first.tuning is not None
    assert first.tuning.total_trials == 3
    assert first.tuning.seed == 42
    assert [
        (trial.state, trial.value, trial.parameters, trial.last_reported_fold)
        for trial in first.tuning.trials
    ] == [
        (trial.state, trial.value, trial.parameters, trial.last_reported_fold)
        for trial in second.tuning.trials
    ]
    assert (
        first_by_name["Ridge Regression (Optuna tuned)"].hyperparameters
        == second_by_name["Ridge Regression (Optuna tuned)"].hyperparameters
    )

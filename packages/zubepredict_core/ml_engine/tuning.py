from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

from sklearn.base import BaseEstimator

from zubepredict_core.ml_engine.candidate_planner import dataset_size_band
from zubepredict_core.shared.schemas import TuningBudget, TuningSummary, TuningTrial


@dataclass
class TuningOutcome:
    evaluations: list[Any]
    factories: dict[str, Callable[[], BaseEstimator]]
    summary: TuningSummary


class _TuningTrialFailed(Exception):
    pass


class TuningPruned(Exception):
    """Stop a trial safely at a completed fold boundary."""


TUNABLE_CANDIDATES = {
    "Logistic Regression",
    "Ridge Regression",
    "Random Forest",
    "Extra Trees",
    "XGBoost",
    "LightGBM",
    "CatBoost",
}


def _positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return cast(int, value)


def resolve_tuning_budget(
    *,
    rows: int,
    requested_trials: int,
    requested_seconds: int,
    experiment_trial_limit: int,
    experiment_time_limit_seconds: int,
    user_trial_limit: int,
    user_time_limit_seconds: int,
    max_candidates: int,
) -> TuningBudget:
    values = {
        "tuning_trials": requested_trials,
        "tuning_timeout_seconds": requested_seconds,
        "experiment trial limit": experiment_trial_limit,
        "experiment time limit": experiment_time_limit_seconds,
        "user trial limit": user_trial_limit,
        "user time limit": user_time_limit_seconds,
        "tuning candidate limit": max_candidates,
    }
    checked = {name: _positive_int(name, value) for name, value in values.items()}
    band = dataset_size_band(rows)
    effective_trials = min(
        checked["tuning_trials"],
        checked["experiment trial limit"],
        checked["user trial limit"],
    )
    effective_seconds = min(
        checked["tuning_timeout_seconds"],
        checked["experiment time limit"],
        checked["user time limit"],
    )
    candidate_limit = checked["tuning candidate limit"]
    reasons: list[str] = []
    if effective_trials < requested_trials:
        reasons.append("The requested trial count was capped by experiment or user policy.")
    if effective_seconds < requested_seconds:
        reasons.append("The requested tuning time was capped by experiment or user policy.")

    if band == "medium":
        reduced_candidates = min(candidate_limit, 2)
    elif band in {"large", "very_large"}:
        reduced_candidates = 1
    else:
        reduced_candidates = candidate_limit
    if reduced_candidates < candidate_limit:
        reasons.append(
            f"Tuning candidates were reduced from {candidate_limit} to {reduced_candidates} "
            f"for a {band} dataset."
        )
    candidate_limit = reduced_candidates

    trial_fraction = {"small": 1.0, "medium": 0.75, "large": 0.5, "very_large": 0.25}[band]
    size_limited_trials = max(1, math.floor(effective_trials * trial_fraction))
    if size_limited_trials < effective_trials:
        reasons.append(
            f"Trials were reduced from {effective_trials} to {size_limited_trials} for a "
            f"{band} dataset."
        )
    effective_trials = size_limited_trials
    if candidate_limit > effective_trials:
        reasons.append(
            f"Tuning candidates were reduced from {candidate_limit} to {effective_trials} so "
            "every selected candidate receives at least one trial."
        )
        candidate_limit = effective_trials

    return TuningBudget(
        requested_trials=requested_trials,
        experiment_trial_limit=experiment_trial_limit,
        user_trial_limit=user_trial_limit,
        effective_max_trials=effective_trials,
        requested_seconds=requested_seconds,
        experiment_time_limit_seconds=experiment_time_limit_seconds,
        user_time_limit_seconds=user_time_limit_seconds,
        effective_time_limit_seconds=effective_seconds,
        candidate_limit=candidate_limit,
        dataset_size_band=band,
        reduction_reasons=reasons,
    )


def _suggest_parameters(trial: Any, name: str) -> dict[str, Any]:
    if name == "Logistic Regression":
        return {"C": trial.suggest_float("C", 1e-3, 100.0, log=True)}
    if name == "Ridge Regression":
        return {"alpha": trial.suggest_float("alpha", 1e-4, 100.0, log=True)}
    if name in {"Random Forest", "Extra Trees"}:
        return {
            "n_estimators": trial.suggest_int("n_estimators", 80, 240, step=40),
            "max_depth": trial.suggest_int("max_depth", 3, 20),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 8),
            "max_features": trial.suggest_float("max_features", 0.4, 1.0),
        }
    if name == "XGBoost":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 80, 240, step=40),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        }
    if name == "LightGBM":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 80, 240, step=40),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 63),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 40),
        }
    if name == "CatBoost":
        return {
            "iterations": trial.suggest_int("iterations", 80, 240, step=40),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "depth": trial.suggest_int("depth", 4, 8),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 10.0, log=True),
        }
    raise ValueError(f"{name} does not have a bounded Stage 10 search space.")


def run_optuna_tuning(
    *,
    ordered_evaluations: list[Any],
    factories: dict[str, Callable[[], BaseEstimator]],
    evaluate: Callable[[str, Callable[[], BaseEstimator], Callable[[int, float], None]], Any],
    direction: Literal["minimize", "maximize"],
    seed: int,
    budget: TuningBudget,
    cancellation_check: Callable[[], bool] | None = None,
) -> TuningOutcome:
    try:
        import optuna
    except ImportError as exc:
        raise RuntimeError("Install the 'ml' extra to enable Optuna tuning.") from exc

    started = time.perf_counter()
    deadline = started + budget.effective_time_limit_seconds
    candidates = [
        item
        for item in ordered_evaluations
        if item.score.status == "completed"
        and item.score.model_name in TUNABLE_CANDIDATES
        and item.score.model_name in factories
    ][: budget.candidate_limit]
    if not candidates:
        return TuningOutcome(
            evaluations=[],
            factories={},
            summary=TuningSummary(
                enabled=True,
                seed=seed,
                budget=budget,
                reason_disabled="No completed candidate has a supported bounded search space.",
            ),
        )

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    tuned_evaluations: list[Any] = []
    tuned_factories: dict[str, Callable[[], BaseEstimator]] = {}
    trial_records: list[TuningTrial] = []
    remaining_trials = budget.effective_max_trials

    for candidate_index, base_evaluation in enumerate(candidates):
        if remaining_trials <= 0 or time.perf_counter() >= deadline:
            break
        if cancellation_check is not None and cancellation_check():
            from zubepredict_core.ml_engine.tournament import TournamentCancelled

            raise TournamentCancelled("Experiment cancellation was requested.")
        remaining_candidates = len(candidates) - candidate_index
        allocated_trials = max(1, remaining_trials // remaining_candidates)
        base_name = base_evaluation.score.model_name
        stored_evaluations: dict[int, Any] = {}
        sampler = optuna.samplers.TPESampler(seed=seed + candidate_index)
        pruner = optuna.pruners.MedianPruner(n_startup_trials=1, n_warmup_steps=1)
        study = optuna.create_study(direction=direction, sampler=sampler, pruner=pruner)

        def objective(
            trial: Any,
            base_name: str = base_name,
            stored_evaluations: dict[int, Any] = stored_evaluations,
        ) -> float:
            if cancellation_check is not None and cancellation_check():
                from zubepredict_core.ml_engine.tournament import TournamentCancelled

                raise TournamentCancelled("Experiment cancellation was requested.")
            if time.perf_counter() >= deadline:
                raise optuna.TrialPruned("The tuning time budget was exhausted.")
            parameters = _suggest_parameters(trial, base_name)

            def factory(parameters: dict[str, Any] = parameters) -> BaseEstimator:
                estimator = factories[base_name]()
                estimator.set_params(**parameters)
                return estimator

            def fold_progress(fold: int, value: float) -> None:
                if cancellation_check is not None and cancellation_check():
                    from zubepredict_core.ml_engine.tournament import TournamentCancelled

                    raise TournamentCancelled("Experiment cancellation was requested.")
                trial.report(value, step=fold)
                if time.perf_counter() >= deadline:
                    raise TuningPruned("The tuning time budget was exhausted.")
                if trial.should_prune():
                    raise TuningPruned(f"Pruned after fold {fold}.")

            try:
                evaluation = evaluate(
                    f"{base_name} Optuna trial {trial.number}", factory, fold_progress
                )
            except TuningPruned as exc:
                raise optuna.TrialPruned(str(exc)) from exc
            if evaluation.score.status != "completed":
                message = evaluation.score.error or "The candidate trial failed."
                trial.set_user_attr("error", message)
                raise _TuningTrialFailed(message)
            stored_evaluations[trial.number] = evaluation
            return float(evaluation.score.mean_score)

        study.optimize(
            objective,
            n_trials=allocated_trials,
            timeout=max(0.001, deadline - time.perf_counter()),
            catch=(_TuningTrialFailed,),
            show_progress_bar=False,
        )
        remaining_trials -= len(study.trials)
        for trial in study.trials:
            state = cast(
                Literal["completed", "pruned", "failed"],
                {"COMPLETE": "completed", "PRUNED": "pruned", "FAIL": "failed"}[trial.state.name],
            )
            last_fold = max(trial.intermediate_values, default=None)
            trial_records.append(
                TuningTrial(
                    candidate_name=base_name,
                    trial_number=trial.number,
                    state=state,
                    value=float(trial.value) if trial.value is not None else None,
                    parameters=dict(trial.params),
                    duration_seconds=(
                        trial.duration.total_seconds() if trial.duration is not None else 0
                    ),
                    last_reported_fold=last_fold,
                    error=trial.user_attrs.get("error"),
                )
            )
        completed = [trial for trial in study.trials if trial.state.name == "COMPLETE"]
        if not completed:
            continue
        best_trial = study.best_trial
        best_evaluation = stored_evaluations[best_trial.number]
        tuned_name = f"{base_name} (Optuna tuned)"
        best_evaluation.score.model_name = tuned_name
        best_evaluation.score.is_tuned = True
        best_evaluation.score.untuned_model_name = base_name
        best_evaluation.score.optuna_trial_number = best_trial.number
        best_evaluation.score.hyperparameters.update(
            {
                "optuna_trial_number": best_trial.number,
                "untuned_model_name": base_name,
            }
        )
        best_parameters = dict(best_trial.params)

        def tuned_factory(
            base_name: str = base_name, parameters: dict[str, Any] = best_parameters
        ) -> BaseEstimator:
            estimator = factories[base_name]()
            estimator.set_params(**parameters)
            return estimator

        tuned_evaluations.append(best_evaluation)
        tuned_factories[tuned_name] = tuned_factory

    states = [trial.state for trial in trial_records]
    summary = TuningSummary(
        enabled=True,
        seed=seed,
        budget=budget,
        candidates_considered=[item.score.model_name for item in candidates],
        total_trials=len(trial_records),
        completed_trials=states.count("completed"),
        pruned_trials=states.count("pruned"),
        failed_trials=states.count("failed"),
        elapsed_seconds=time.perf_counter() - started,
        trials=trial_records,
    )
    return TuningOutcome(
        evaluations=tuned_evaluations,
        factories=tuned_factories,
        summary=summary,
    )

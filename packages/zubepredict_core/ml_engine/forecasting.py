from __future__ import annotations

import math
import platform
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset

from zubepredict_core.ml_engine.tournament import TournamentCancelled
from zubepredict_core.shared.schemas import (
    ForecastCandidateScore,
    ForecastContract,
    ForecastFoldScore,
    ForecastPoint,
    ForecastResult,
    MetricSummary,
    TaskDecision,
    TaskType,
)

ForecastOutput = tuple[
    np.ndarray[Any, Any],
    np.ndarray[Any, Any] | None,
    np.ndarray[Any, Any] | None,
]


class ForecastClarificationRequired(ValueError):
    """Raised when a required forecasting choice needs user confirmation."""


@dataclass(frozen=True)
class _ForecastCandidate:
    name: str
    family: str
    hyperparameters: dict[str, Any]
    supports_intervals: bool
    forecast: Callable[[np.ndarray[Any, Any], int, int], ForecastOutput]


@dataclass(frozen=True)
class _PreparedForecast:
    series: pd.Series
    contract: ForecastContract


def _software_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for package in ("numpy", "pandas", "statsmodels"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            continue
    return versions


def _decision_time_column(decision: TaskDecision) -> str | None:
    for evidence in decision.evidence:
        if evidence.code == "forecast_time_column" and isinstance(evidence.value, str):
            return evidence.value
    return None


def _default_seasonal_period(frequency: str) -> int | None:
    name = to_offset(frequency).name.upper()
    if name == "H":
        return 24
    if name in {"MIN", "T"}:
        return 60
    if name == "D":
        return 7
    if name == "B":
        return 5
    if name.startswith("W"):
        return 52
    if name in {"M", "ME", "MS"}:
        return 12
    if name in {"Q", "QE", "QS"}:
        return 4
    return None


def _required_positive_int(configuration: dict[str, Any], key: str) -> int:
    value = configuration.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        raise ForecastClarificationRequired(
            f"Confirm '{key}' as a positive whole number before forecasting."
        )
    if parsed < 1:
        raise ForecastClarificationRequired(
            f"Confirm '{key}' as a positive whole number before forecasting."
        )
    return parsed


def prepare_forecast_contract(
    df: pd.DataFrame,
    decision: TaskDecision,
    configuration: dict[str, Any],
    *,
    max_horizon: int = 365,
) -> _PreparedForecast:
    if decision.task_type != TaskType.TIME_SERIES_FORECASTING:
        raise ValueError("A forecasting contract requires a time-series task decision.")
    target_column = decision.target_column
    if not target_column or target_column not in df.columns:
        raise ForecastClarificationRequired(
            "Confirm one existing numeric target column before forecasting."
        )
    configured_time = configuration.get("time_column")
    time_column = (
        str(configured_time).strip() if configured_time else _decision_time_column(decision)
    )
    if not time_column or time_column not in df.columns:
        raise ForecastClarificationRequired(
            "Confirm one existing date/time column in configuration.time_column."
        )
    horizon = _required_positive_int(configuration, "forecast_horizon")
    if horizon > max_horizon:
        raise ForecastClarificationRequired(
            f"The forecast horizon exceeds the configured maximum of {max_horizon}."
        )

    timestamps = pd.to_datetime(df[time_column], errors="coerce", utc=True)
    if timestamps.isna().any():
        raise ForecastClarificationRequired(
            f"Time column '{time_column}' contains values that are not valid timestamps."
        )
    if timestamps.duplicated().any():
        raise ForecastClarificationRequired(
            "Duplicate timestamps require an explicit aggregation decision before forecasting."
        )
    was_sorted = bool(timestamps.is_monotonic_increasing)
    order = np.argsort(timestamps.to_numpy())
    ordered_times = pd.DatetimeIndex(timestamps.iloc[order])

    target_source = df[target_column]
    numeric_target = pd.to_numeric(target_source, errors="coerce")
    invalid_numeric = target_source.notna() & numeric_target.isna()
    if invalid_numeric.any():
        raise ForecastClarificationRequired(
            f"Forecast target '{target_column}' contains non-numeric observed values."
        )
    ordered_target = pd.Series(
        numeric_target.iloc[order].to_numpy(dtype=float), index=ordered_times, name=target_column
    )

    configured_frequency = configuration.get("frequency")
    if configured_frequency:
        try:
            frequency = to_offset(str(configured_frequency)).freqstr
        except ValueError as exc:
            raise ForecastClarificationRequired(
                "Confirm configuration.frequency using a valid pandas frequency such as "
                "D, W, or MS."
            ) from exc
        frequency_source: Literal["confirmed", "inferred"] = "confirmed"
    else:
        inferred = pd.infer_freq(ordered_times) if len(ordered_times) >= 3 else None
        if inferred is None:
            raise ForecastClarificationRequired(
                "The frequency could not be inferred because timestamps are irregular or gapped; "
                "confirm configuration.frequency."
            )
        frequency = to_offset(inferred).freqstr
        frequency_source = "inferred"

    regular_index = pd.date_range(
        start=ordered_times[0], end=ordered_times[-1], freq=frequency, tz="UTC"
    )
    incompatible = ordered_times.difference(regular_index)
    if len(incompatible):
        raise ForecastClarificationRequired(
            f"Some timestamps do not align with the confirmed '{frequency}' frequency."
        )
    regular_series = ordered_target.reindex(regular_index)
    first_observed = regular_series.first_valid_index()
    if first_observed is None:
        raise ForecastClarificationRequired("The forecast target has no observed numeric values.")
    regular_series = regular_series.loc[first_observed:]
    gap_count = len(regular_index) - len(ordered_times)

    configured_period = configuration.get("seasonal_period")
    if configured_period is not None:
        seasonal_period = _required_positive_int(configuration, "seasonal_period")
    else:
        inferred_period = _default_seasonal_period(frequency)
        if inferred_period is None:
            raise ForecastClarificationRequired(
                "Confirm configuration.seasonal_period for this frequency."
            )
        seasonal_period = inferred_period
    if seasonal_period < 2:
        raise ForecastClarificationRequired("Seasonal period must be at least 2.")

    minimum_rows = max(12, seasonal_period * 2 + 3)
    if len(regular_series) < minimum_rows:
        raise ForecastClarificationRequired(
            f"Forecasting at seasonal period {seasonal_period} requires at least "
            f"{minimum_rows} regular time steps."
        )
    return _PreparedForecast(
        series=regular_series,
        contract=ForecastContract(
            time_column=time_column,
            target_column=target_column,
            frequency=frequency,
            frequency_source=frequency_source,
            horizon=horizon,
            seasonal_period=seasonal_period,
            original_rows=len(df),
            regularized_rows=len(regular_series),
            gap_count=gap_count,
            missing_target_count=int(regular_series.isna().sum()),
            was_sorted=was_sorted,
        ),
    )


def _naive(train: np.ndarray[Any, Any], steps: int, period: int) -> ForecastOutput:
    del period
    return np.repeat(train[-1], steps), None, None


def _seasonal_naive(train: np.ndarray[Any, Any], steps: int, period: int) -> ForecastOutput:
    if len(train) < period:
        raise ValueError("Seasonal-naive training data is shorter than one seasonal period.")
    predictions = np.asarray([train[-period + (offset % period)] for offset in range(steps)])
    return predictions, None, None


def _holt_winters(train: np.ndarray[Any, Any], steps: int, period: int) -> ForecastOutput:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = ExponentialSmoothing(
            train,
            trend="add",
            seasonal="add",
            seasonal_periods=period,
            initialization_method="estimated",
        ).fit(optimized=True, use_brute=False)
    return np.asarray(fitted.forecast(steps), dtype=float), None, None


def _sarimax_forecast(
    train: np.ndarray[Any, Any],
    steps: int,
    period: int,
    *,
    seasonal: bool,
    max_iterations: int,
) -> ForecastOutput:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    seasonal_order = (1, 0, 0, period) if seasonal else (0, 0, 0, 0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = SARIMAX(
            train,
            order=(1, 1, 1),
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False, maxiter=max_iterations)
        prediction = fitted.get_forecast(steps=steps)
    intervals = np.asarray(prediction.conf_int(alpha=0.05), dtype=float)
    return (
        np.asarray(prediction.predicted_mean, dtype=float),
        intervals[:, 0],
        intervals[:, 1],
    )


def _forecast_candidates(max_arima_iterations: int) -> list[_ForecastCandidate]:
    return [
        _ForecastCandidate("Naive Baseline", "naive", {}, False, _naive),
        _ForecastCandidate("Seasonal Naive Baseline", "seasonal_naive", {}, False, _seasonal_naive),
        _ForecastCandidate(
            "Holt-Winters",
            "holt_winters",
            {"trend": "add", "seasonal": "add"},
            False,
            _holt_winters,
        ),
        _ForecastCandidate(
            "ARIMA(1,1,1)",
            "arima",
            {"order": [1, 1, 1]},
            True,
            lambda train, steps, period: _sarimax_forecast(
                train,
                steps,
                period,
                seasonal=False,
                max_iterations=max_arima_iterations,
            ),
        ),
        _ForecastCandidate(
            "SARIMA(1,1,1)x(1,0,0,s)",
            "sarima",
            {"order": [1, 1, 1], "seasonal_order": [1, 0, 0, "seasonal_period"]},
            True,
            lambda train, steps, period: _sarimax_forecast(
                train,
                steps,
                period,
                seasonal=True,
                max_iterations=max_arima_iterations,
            ),
        ),
    ]


def _rolling_origins(
    length: int, horizon: int, seasonal_period: int, maximum_folds: int
) -> list[tuple[int, int]]:
    validation_rows = min(horizon, max(1, length // 10))
    minimum_train = max(12, seasonal_period * 2)
    fold_count = min(maximum_folds, (length - minimum_train) // validation_rows)
    if fold_count < 2:
        raise ForecastClarificationRequired(
            "The series is too short for at least two rolling-origin validation folds."
        )
    first_start = length - fold_count * validation_rows
    return [(first_start + fold * validation_rows, validation_rows) for fold in range(fold_count)]


def _fold_metrics(
    actual: np.ndarray[Any, Any], predicted: np.ndarray[Any, Any]
) -> dict[str, float]:
    errors = actual - predicted
    denominator = np.abs(actual) + np.abs(predicted)
    smape_terms = np.where(denominator > 1e-12, 2 * np.abs(errors) / denominator, 0)
    return {
        "root_mean_squared_error": float(np.sqrt(np.mean(errors**2))),
        "mean_absolute_error": float(np.mean(np.abs(errors))),
        "symmetric_mean_absolute_percentage_error": float(np.mean(smape_terms) * 100),
    }


def _metric_summary(values: list[float]) -> MetricSummary:
    mean = float(np.mean(values))
    standard_deviation = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    margin = 1.96 * standard_deviation / math.sqrt(len(values)) if values else 0.0
    return MetricSummary(
        mean=mean,
        standard_deviation=standard_deviation,
        confidence_interval_95=(mean - margin, mean + margin),
        fold_values=values,
    )


def _evaluate_candidate(
    series: pd.Series,
    origins: list[tuple[int, int]],
    candidate: _ForecastCandidate,
    seasonal_period: int,
    cancellation_check: Callable[[], bool] | None,
) -> ForecastCandidateScore:
    fold_scores: list[ForecastFoldScore] = []
    metric_values: dict[str, list[float]] = {}
    total_fit_seconds = 0.0
    try:
        for fold, (validation_start, validation_rows) in enumerate(origins, start=1):
            if cancellation_check is not None and cancellation_check():
                raise TournamentCancelled("Experiment cancellation was requested.")
            train_series = series.iloc[:validation_start].ffill()
            validation = series.iloc[validation_start : validation_start + validation_rows]
            observed = validation.notna().to_numpy()
            if not observed.any():
                raise ValueError(f"Validation fold {fold} contains no observed target values.")
            train = train_series.to_numpy(dtype=float)
            started = time.perf_counter()
            predicted, _, _ = candidate.forecast(train, validation_rows, seasonal_period)
            fit_seconds = time.perf_counter() - started
            total_fit_seconds += fit_seconds
            metrics = _fold_metrics(validation.to_numpy(dtype=float)[observed], predicted[observed])
            for name, value in metrics.items():
                metric_values.setdefault(name, []).append(value)
            fold_scores.append(
                ForecastFoldScore(
                    fold=fold,
                    train_rows=len(train),
                    validation_rows=int(observed.sum()),
                    train_end=series.index[validation_start - 1].isoformat(),
                    validation_start=validation.index[0].isoformat(),
                    validation_end=validation.index[-1].isoformat(),
                    metrics=metrics,
                    fit_seconds=fit_seconds,
                )
            )
        summaries = {name: _metric_summary(values) for name, values in metric_values.items()}
        return ForecastCandidateScore(
            model_name=candidate.name,
            family=candidate.family,
            mean_score=summaries["root_mean_squared_error"].mean,
            fit_seconds=total_fit_seconds,
            hyperparameters=candidate.hyperparameters,
            metrics=summaries,
            fold_scores=fold_scores,
            supports_prediction_intervals=candidate.supports_intervals,
        )
    except TournamentCancelled:
        raise
    except Exception as exc:
        return ForecastCandidateScore(
            model_name=candidate.name,
            family=candidate.family,
            fit_seconds=total_fit_seconds,
            status="failed",
            error=str(exc)[:500],
            failure_stage=f"rolling_origin_fold_{len(fold_scores) + 1}",
            hyperparameters=candidate.hyperparameters,
            fold_scores=fold_scores,
            supports_prediction_intervals=candidate.supports_intervals,
        )


def run_forecasting_tournament(
    df: pd.DataFrame,
    decision: TaskDecision,
    configuration: dict[str, Any],
    *,
    seed: int = 42,
    max_horizon: int = 365,
    validation_folds: int = 3,
    max_arima_iterations: int = 50,
    compute_budget_seconds: int = 600,
    progress_callback: Callable[[int, str], None] | None = None,
    cancellation_check: Callable[[], bool] | None = None,
) -> ForecastResult:
    prepared = prepare_forecast_contract(df, decision, configuration, max_horizon=max_horizon)
    series = prepared.series
    contract = prepared.contract
    origins = _rolling_origins(
        len(series), contract.horizon, contract.seasonal_period, validation_folds
    )
    candidates = _forecast_candidates(max_arima_iterations)
    evaluations: list[ForecastCandidateScore] = []
    started = time.perf_counter()
    for index, candidate in enumerate(candidates):
        if cancellation_check is not None and cancellation_check():
            raise TournamentCancelled("Experiment cancellation was requested.")
        if time.perf_counter() - started >= compute_budget_seconds:
            evaluations.append(
                ForecastCandidateScore(
                    model_name=candidate.name,
                    family=candidate.family,
                    status="failed",
                    error="The compute budget was exhausted before evaluation.",
                    failure_stage="resource_budget",
                    hyperparameters=candidate.hyperparameters,
                    supports_prediction_intervals=candidate.supports_intervals,
                )
            )
            continue
        if progress_callback is not None:
            progress_callback(25 + int(index / len(candidates) * 60), candidate.name)
        evaluations.append(
            _evaluate_candidate(
                series,
                origins,
                candidate,
                contract.seasonal_period,
                cancellation_check,
            )
        )

    successful = [
        score
        for score in evaluations
        if score.status == "completed" and score.mean_score is not None
    ]
    successful.sort(key=lambda score: score.mean_score or math.inf)
    failed = [score for score in evaluations if score not in successful]
    ordered = [*successful, *failed]
    full_train = series.ffill().to_numpy(dtype=float)
    by_family = {candidate.family: candidate for candidate in candidates}
    winner: ForecastCandidateScore | None = None
    final_output: ForecastOutput | None = None
    for score in successful:
        if cancellation_check is not None and cancellation_check():
            raise TournamentCancelled("Experiment cancellation was requested.")
        try:
            final_output = by_family[score.family].forecast(
                full_train, contract.horizon, contract.seasonal_period
            )
            winner = score
            break
        except Exception as exc:
            score.status = "failed"
            score.failure_stage = "final_fit"
            score.error = str(exc)[:500]
    successful_after_fit = [
        score for score in ordered if score.status == "completed" and score.mean_score is not None
    ]
    successful_after_fit.sort(key=lambda score: score.mean_score or math.inf)
    ordered = [
        *successful_after_fit,
        *(score for score in ordered if score not in successful_after_fit),
    ]
    forecasts: list[ForecastPoint] = []
    if winner is not None and final_output is not None:
        predicted, lower, upper = final_output
        future_index = pd.date_range(
            start=series.index[-1],
            periods=contract.horizon + 1,
            freq=contract.frequency,
        )[1:]
        forecasts = [
            ForecastPoint(
                timestamp=timestamp.isoformat(),
                predicted=float(predicted[position]),
                lower_95=float(lower[position]) if lower is not None else None,
                upper_95=float(upper[position]) if upper is not None else None,
            )
            for position, timestamp in enumerate(future_index)
        ]

    warnings_list = [
        "Forecasts extend historical patterns and do not establish causality or guarantee outcomes."
    ]
    if contract.gap_count:
        warnings_list.append(
            f"Detected {contract.gap_count} missing time step(s); training folds used past-only "
            "forward filling and validation scored observed targets only."
        )
    if winner is not None and not winner.supports_prediction_intervals:
        warnings_list.append(
            "The selected model does not provide a supported analytical prediction interval."
        )
    if winner is None:
        warnings_list.append("Every forecasting candidate failed; no future forecast was produced.")
    return ForecastResult(
        task=decision,
        primary_metric="root_mean_squared_error",
        selection_rule=(
            "Lowest mean rolling-origin RMSE; the leaderboard also reports fold variability, "
            "MAE, sMAPE, and the exact expanding-window boundaries."
        ),
        leaderboard=ordered,
        winner=winner.model_name if winner else None,
        contract=contract,
        forecast=forecasts,
        warnings=warnings_list,
        validation_strategy=(
            f"{len(origins)} expanding-window rolling-origin folds with "
            f"{origins[0][1]} future step(s) per fold"
        ),
        random_seed=seed,
        software_versions=_software_versions(),
    )

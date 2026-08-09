from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from zubepredict_core.ml_engine import forecasting
from zubepredict_core.ml_engine.forecasting import (
    ForecastClarificationRequired,
    prepare_forecast_contract,
    run_forecasting_tournament,
)
from zubepredict_core.ml_engine.tournament import TournamentCancelled
from zubepredict_core.shared.schemas import (
    DecisionEvidence,
    TaskDecision,
    TaskType,
)


def forecast_decision() -> TaskDecision:
    return TaskDecision(
        task_type=TaskType.TIME_SERIES_FORECASTING,
        target_column="demand",
        confidence=1,
        reasons=["explicit forecasting test"],
        evidence=[
            DecisionEvidence(
                code="forecast_time_column",
                message="Date is the confirmed ordering column.",
                effect="support",
                value="date",
            )
        ],
    )


def daily_series(rows: int = 56) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=rows, freq="D", tz="UTC")
    demand = [20 + (index % 7) * 3 + index * 0.1 for index in range(rows)]
    return pd.DataFrame({"date": dates, "demand": demand})


def test_forecast_contract_requires_explicit_horizon() -> None:
    with pytest.raises(ForecastClarificationRequired, match="forecast_horizon"):
        prepare_forecast_contract(daily_series(), forecast_decision(), {})


def test_irregular_series_requires_frequency_confirmation() -> None:
    dataframe = daily_series().drop(index=10).reset_index(drop=True)

    with pytest.raises(ForecastClarificationRequired, match="frequency could not be inferred"):
        prepare_forecast_contract(
            dataframe,
            forecast_decision(),
            {"forecast_horizon": 3},
        )


def test_regular_frequency_is_inferred_with_a_safe_seasonal_default() -> None:
    prepared = prepare_forecast_contract(
        daily_series(),
        forecast_decision(),
        {"forecast_horizon": 3},
    )

    assert prepared.contract.frequency == "D"
    assert prepared.contract.frequency_source == "inferred"
    assert prepared.contract.seasonal_period == 7


def test_contract_sorts_time_identifies_gaps_and_never_backfills() -> None:
    dataframe = daily_series().drop(index=10).iloc[::-1].reset_index(drop=True)

    prepared = prepare_forecast_contract(
        dataframe,
        forecast_decision(),
        {"forecast_horizon": 3, "frequency": "D"},
    )

    assert prepared.contract.was_sorted is False
    assert prepared.contract.gap_count == 1
    assert prepared.contract.missing_target_count == 1
    assert prepared.series.index.is_monotonic_increasing
    assert pd.isna(prepared.series.iloc[10])


def test_duplicate_timestamps_require_aggregation_decision() -> None:
    dataframe = daily_series()
    dataframe.loc[1, "date"] = dataframe.loc[0, "date"]

    with pytest.raises(ForecastClarificationRequired, match="aggregation"):
        prepare_forecast_contract(
            dataframe,
            forecast_decision(),
            {"forecast_horizon": 3, "frequency": "D"},
        )


def test_forecasting_tournament_has_time_aware_folds_and_both_baselines() -> None:
    dataframe = daily_series()

    result = run_forecasting_tournament(
        dataframe,
        forecast_decision(),
        {"forecast_horizon": 4, "frequency": "D"},
        max_arima_iterations=15,
    )

    by_family = {score.family: score for score in result.leaderboard}
    assert result.winner is not None
    assert {"naive", "seasonal_naive", "holt_winters", "arima", "sarima"} == set(by_family)
    assert by_family["naive"].status == "completed"
    assert by_family["seasonal_naive"].status == "completed"
    assert len(by_family["naive"].fold_scores) == 3
    assert by_family["naive"].metrics["root_mean_squared_error"].standard_deviation >= 0
    for fold in by_family["naive"].fold_scores:
        assert datetime.fromisoformat(fold.train_end) < datetime.fromisoformat(
            fold.validation_start
        )
    assert len(result.forecast) == 4
    assert datetime.fromisoformat(result.forecast[0].timestamp) > dataframe["date"].max()
    assert "rolling-origin" in result.validation_strategy


def test_arima_produces_supported_prediction_intervals() -> None:
    values = np.asarray([10 + index * 0.2 + (index % 7) for index in range(50)], dtype=float)

    predicted, lower, upper = forecasting._sarimax_forecast(
        values,
        3,
        7,
        seasonal=False,
        max_iterations=15,
    )

    assert len(predicted) == 3
    assert lower is not None and upper is not None
    assert np.all(lower <= predicted)
    assert np.all(predicted <= upper)


def test_naive_and_seasonal_naive_forecasts_are_distinct() -> None:
    values = np.asarray([1, 2, 3, 4, 5, 6, 7, 8], dtype=float)

    naive, _, _ = forecasting._naive(values, 3, 3)
    seasonal, _, _ = forecasting._seasonal_naive(values, 4, 3)

    assert naive.tolist() == [8, 8, 8]
    assert seasonal.tolist() == [6, 7, 8, 6]


def test_failed_forecast_candidate_is_isolated(monkeypatch) -> None:
    original = forecasting._forecast_candidates

    def broken(train, steps, period):
        raise RuntimeError("forecast candidate failed")

    def candidates(iterations):
        return [
            *original(iterations),
            forecasting._ForecastCandidate("Broken", "broken", {}, False, broken),
        ]

    monkeypatch.setattr(forecasting, "_forecast_candidates", candidates)

    result = run_forecasting_tournament(
        daily_series(),
        forecast_decision(),
        {"forecast_horizon": 3, "frequency": "D"},
        max_arima_iterations=10,
    )

    failed = next(score for score in result.leaderboard if score.family == "broken")
    assert result.winner is not None
    assert failed.status == "failed"
    assert failed.error == "forecast candidate failed"


def test_forecasting_honours_cancellation() -> None:
    with pytest.raises(TournamentCancelled):
        run_forecasting_tournament(
            daily_series(),
            forecast_decision(),
            {"forecast_horizon": 3, "frequency": "D"},
            cancellation_check=lambda: True,
        )

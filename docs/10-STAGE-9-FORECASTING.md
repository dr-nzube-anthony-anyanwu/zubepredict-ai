# Stage 9: Time-Series Forecasting

Stage 9 adds deterministic, leakage-safe univariate forecasting to the existing
Stage 7 worker. Queue messages still contain only experiment, owner and job
identifiers. Forecasting runs only when the confirmed task is
`time_series_forecasting`.

## Forecast contract

The experiment must identify a numeric target and a parseable time column. The
forecast horizon is always explicit and must be a positive integer no larger
than the configured server limit. A typical experiment configuration is:

```json
{
  "time_column": "date",
  "frequency": "D",
  "forecast_horizon": 14,
  "seasonal_period": 7
}
```

The time column may come from the confirmed Stage 4 decision evidence instead
of `time_column`. A regular frequency may be inferred from the timestamps; an
irregular series requires the user to confirm `frequency`. Common regular
frequencies receive conservative seasonal defaults, while
`seasonal_period` remains configurable.

Duplicate timestamps are not aggregated silently because sum, mean, last and
other policies have different meanings. Such a dataset needs an explicit data
preparation decision before it can be forecast.

## Leakage and missing time steps

Rows are sorted by time and regularised to the confirmed frequency. Gaps are
reported in the result contract. Training folds use only past-value forward
filling; the engine never fills a past row from a future observation. Validation
metrics use only target values that were actually observed.

Validation uses expanding-window rolling origins. Every validation interval is
strictly later than its training interval, and model selection uses the lowest
mean rolling-origin root mean squared error (RMSE). Fold-level RMSE, mean
absolute error, symmetric mean absolute percentage error, timing and exact time
boundaries remain visible in the evidence.

## Candidates and forecast output

The bounded tournament compares:

- naive last-value baseline;
- seasonal-naive baseline;
- additive Holt-Winters;
- ARIMA(1,1,1);
- SARIMA(1,1,1)x(1,0,0,s).

Candidate failures are isolated. ARIMA and SARIMA use their fitted forecast
distribution to return 95% prediction intervals. The other candidates do not
invent unsupported intervals, and the result warns when the selected candidate
has none. Forecasts describe continuation of historical patterns; they do not
establish causality or guarantee future outcomes.

The durable experiment result stores the contract, leaderboard, fold evidence
and forecast count. The complete timestamped forecast is uploaded as
`forecast.json` under the existing owner/job prefix in the private Supabase
artifacts bucket. Server-side storage access continues to use the service role;
no privileged key is exposed to the browser or queue payload.

If required configuration is missing, the worker moves the experiment to
`needs_clarification` with the missing fields in its structured result. Until a
later orchestration stage adds pause/resume interaction, submit a new experiment
with the completed configuration.

## Verification

```powershell
$env:PYTHONPATH="$PWD;$PWD\packages;$PWD\apps\api"
.\.venv\Scripts\pytest.exe tests\unit\test_forecasting.py -q
.\scripts\test.ps1
```

No Stage 9 database migration, account or new secret is required. It reuses the
existing experiments, model-runs, fold-metrics and private-artifact facilities.

References: [pandas frequency inference](https://pandas.pydata.org/docs/reference/api/pandas.infer_freq.html),
[statsmodels Holt-Winters results](https://www.statsmodels.org/stable/generated/statsmodels.tsa.holtwinters.HoltWintersResults.html),
and [statsmodels SARIMAX](https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html).

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskType(StrEnum):
    BINARY_CLASSIFICATION = "binary_classification"
    MULTICLASS_CLASSIFICATION = "multiclass_classification"
    REGRESSION = "regression"
    CLUSTERING = "clustering"
    ANOMALY_DETECTION = "anomaly_detection"
    TIME_SERIES_FORECASTING = "time_series_forecasting"
    NEEDS_CLARIFICATION = "needs_clarification"


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    missing_count: int
    missing_percent: float
    unique_count: int
    sample_values: list[Any] = Field(default_factory=list)
    suspected_identifier: bool = False


class DatasetProfile(BaseModel):
    rows: int
    columns: int
    duplicate_rows: int
    column_profiles: list[ColumnProfile]
    possible_targets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    quality_report: DataQualityReport | None = None


class QualityFinding(BaseModel):
    id: str
    code: str
    severity: Literal["blocking", "warning"]
    message: str
    columns: list[str] = Field(default_factory=list)
    metric: float | int | str | None = None
    suggested_action: str
    requires_acknowledgement: bool = False
    acknowledged: bool = False


class DataQualityReport(BaseModel):
    rows: int
    columns: int
    target_column: str | None = None
    findings: list[QualityFinding] = Field(default_factory=list)
    blocking_errors: list[QualityFinding] = Field(default_factory=list)
    warnings: list[QualityFinding] = Field(default_factory=list)
    suggested_exclusions: list[str] = Field(default_factory=list)
    forbidden_features: list[str] = Field(default_factory=list)
    group_columns: list[str] = Field(default_factory=list)
    time_columns: list[str] = Field(default_factory=list)
    acknowledged_risks: list[str] = Field(default_factory=list)
    can_train: bool
    evidence_hash: str


class DecisionEvidence(BaseModel):
    code: str
    message: str
    effect: Literal["support", "concern", "block"]
    value: str | int | float | bool | None = None


class TargetCandidate(BaseModel):
    column: str
    score: float = Field(ge=0, le=1)
    suitable: bool
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class TaskSuggestion(BaseModel):
    provider: str
    task_type: TaskType
    target_column: str | None = None
    rationale: str


class TaskDecision(BaseModel):
    task_type: TaskType
    target_column: str | None = None
    confidence: float = Field(ge=0, le=1)
    reasons: list[str]
    clarification_question: str | None = None
    evidence: list[DecisionEvidence] = Field(default_factory=list)
    target_candidates: list[TargetCandidate] = Field(default_factory=list)
    confidence_reasons: list[str] = Field(default_factory=list)
    requires_clarification: bool = False
    evidence_hash: str = ""
    decision_source: Literal["deterministic", "user_override"] = "deterministic"
    optional_suggestion: TaskSuggestion | None = None
    suggestion_used: bool = False


class ModelScore(BaseModel):
    model_name: str
    primary_metric: str
    mean_score: float
    score_std: float
    fit_seconds: float
    status: str = "completed"
    error: str | None = None
    failure_stage: str | None = None
    metrics: dict[str, MetricSummary] = Field(default_factory=dict)
    fold_scores: list[FoldScore] = Field(default_factory=list)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    is_tuned: bool = False
    untuned_model_name: str | None = None
    optuna_trial_number: int | None = None


class MetricSummary(BaseModel):
    mean: float
    standard_deviation: float
    confidence_interval_95: tuple[float, float]
    fold_values: list[float] = Field(default_factory=list)


class FoldScore(BaseModel):
    fold: int
    train_rows: int
    validation_rows: int
    metrics: dict[str, float]
    fit_seconds: float
    predict_seconds: float


class CandidatePlanEntry(BaseModel):
    name: str
    family: str
    selected: bool
    reason: str


class CandidatePlan(BaseModel):
    rows: int
    usable_features: int
    numeric_features: int
    categorical_features: int
    estimated_encoded_features: int
    sparse_expected: bool
    imbalance_ratio: float | None = None
    compute_budget_seconds: int
    max_models: int
    requested_max_models: int = 0
    dataset_size_band: Literal["small", "medium", "large", "very_large"] = "small"
    reduction_reason: str | None = None
    candidates: list[CandidatePlanEntry] = Field(default_factory=list)


class TuningBudget(BaseModel):
    requested_trials: int
    experiment_trial_limit: int
    user_trial_limit: int
    effective_max_trials: int
    requested_seconds: int
    experiment_time_limit_seconds: int
    user_time_limit_seconds: int
    effective_time_limit_seconds: int
    candidate_limit: int
    dataset_size_band: Literal["small", "medium", "large", "very_large"]
    reduction_reasons: list[str] = Field(default_factory=list)


class TuningTrial(BaseModel):
    candidate_name: str
    trial_number: int
    state: Literal["completed", "pruned", "failed"]
    value: float | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    duration_seconds: float = 0
    last_reported_fold: int | None = None
    error: str | None = None


class TuningSummary(BaseModel):
    enabled: bool
    seed: int
    sampler: str = "TPESampler"
    pruner: str = "MedianPruner"
    budget: TuningBudget | None = None
    candidates_considered: list[str] = Field(default_factory=list)
    total_trials: int = 0
    completed_trials: int = 0
    pruned_trials: int = 0
    failed_trials: int = 0
    elapsed_seconds: float = 0
    trials: list[TuningTrial] = Field(default_factory=list)
    reason_disabled: str | None = None


class OutOfFoldPrediction(BaseModel):
    row_index: str
    fold: int
    actual: Any
    predicted: Any
    positive_probability: float | None = None
    class_probabilities: dict[str, float] = Field(default_factory=dict)


class CalibrationBin(BaseModel):
    mean_predicted_probability: float
    observed_positive_rate: float


class CalibrationSummary(BaseModel):
    positive_label: str
    brier_score: float
    expected_calibration_error: float
    bins: list[CalibrationBin] = Field(default_factory=list)


class ThresholdPoint(BaseModel):
    threshold: float
    precision: float
    recall: float
    f1: float


class ThresholdAnalysis(BaseModel):
    positive_label: str
    recommended_threshold: float
    recommendation_basis: str
    points: list[ThresholdPoint] = Field(default_factory=list)


class ArtifactManifest(BaseModel):
    path: str
    format: Literal["skops"] = "skops"
    sha256: str
    size_bytes: int
    untrusted_types: list[str] = Field(default_factory=list)


class FeatureImportance(BaseModel):
    feature: str
    importance: float
    standard_deviation: float | None = None


class FeatureContribution(BaseModel):
    feature: str
    contribution: float


class LocalExplanation(BaseModel):
    row_index: str
    actual: Any
    predicted: Any
    explained_output: str
    contributions: list[FeatureContribution] = Field(default_factory=list)
    caveat: str


class ExplanationEvidence(BaseModel):
    method: str
    model_name: str
    sampled_rows: int
    background_rows: int
    encoded_feature_count: int
    global_importance: list[FeatureImportance] = Field(default_factory=list)
    local_explanations: list[LocalExplanation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    random_seed: int


class PlotSeries(BaseModel):
    name: str
    x: list[Any] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)


class DiagnosticPlot(BaseModel):
    plot_id: str
    kind: Literal[
        "confusion_matrix",
        "roc_curve",
        "precision_recall_curve",
        "calibration_curve",
        "residuals",
        "actual_vs_predicted",
        "learning_curve",
    ]
    title: str
    x_label: str
    y_label: str
    series: list[PlotSeries] = Field(default_factory=list)
    matrix: list[list[int]] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    caveat: str


class SegmentError(BaseModel):
    feature: str
    segment: str
    rows: int
    metric_name: Literal["error_rate", "mean_absolute_error"]
    metric_value: float
    overall_metric_value: float
    difference_from_overall: float
    caveat: str


class ErrorAnalysisEvidence(BaseModel):
    source: str = "out_of_fold_predictions"
    plots: list[DiagnosticPlot] = Field(default_factory=list)
    segments: list[SegmentError] = Field(default_factory=list)
    protected_columns_skipped: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExperimentResult(BaseModel):
    task: TaskDecision
    primary_metric: str
    leaderboard: list[ModelScore]
    winner: str | None
    warnings: list[str] = Field(default_factory=list)
    quality_report: DataQualityReport | None = None
    validation_strategy: str = ""
    candidate_plan: CandidatePlan | None = None
    tuning: TuningSummary | None = None
    out_of_fold_predictions: list[OutOfFoldPrediction] = Field(default_factory=list)
    calibration: CalibrationSummary | None = None
    threshold_analysis: ThresholdAnalysis | None = None
    explanations: ExplanationEvidence | None = None
    error_analysis: ErrorAnalysisEvidence | None = None
    winner_artifact: ArtifactManifest | None = None
    fitted_winner: bool = False
    random_seed: int | None = None
    software_versions: dict[str, str] = Field(default_factory=dict)


class UnsupervisedSuitability(BaseModel):
    rows: int
    original_columns: int
    usable_columns: list[str] = Field(default_factory=list)
    numeric_columns: list[str] = Field(default_factory=list)
    categorical_columns: list[str] = Field(default_factory=list)
    excluded_columns: list[str] = Field(default_factory=list)
    estimated_encoded_features: int = 0
    can_run: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class UnsupervisedCandidateScore(BaseModel):
    model_name: str
    family: str
    primary_metric: str
    selection_score: float | None = None
    fit_seconds: float = 0
    status: Literal["completed", "failed"] = "completed"
    error: str | None = None
    failure_stage: str | None = None
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    stability_scores: list[float] = Field(default_factory=list)


class UnsupervisedAssignment(BaseModel):
    row_index: str
    label: int
    anomaly: bool = False
    anomaly_score: float | None = None


class SegmentDescription(BaseModel):
    segment_label: int
    size: int
    fraction: float
    distinguishing_features: list[str] = Field(default_factory=list)
    caveat: str


class UnsupervisedResult(BaseModel):
    task: TaskDecision
    primary_metric: str
    selection_rule: str
    leaderboard: list[UnsupervisedCandidateScore]
    winner: str | None
    suitability: UnsupervisedSuitability
    assignments: list[UnsupervisedAssignment] = Field(default_factory=list)
    segment_descriptions: list[SegmentDescription] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_strategy: str
    random_seed: int
    software_versions: dict[str, str] = Field(default_factory=dict)


class ForecastContract(BaseModel):
    time_column: str
    target_column: str
    frequency: str
    frequency_source: Literal["confirmed", "inferred"]
    horizon: int
    seasonal_period: int
    original_rows: int
    regularized_rows: int
    gap_count: int
    missing_target_count: int
    was_sorted: bool


class ForecastFoldScore(BaseModel):
    fold: int
    train_rows: int
    validation_rows: int
    train_end: str
    validation_start: str
    validation_end: str
    metrics: dict[str, float]
    fit_seconds: float


class ForecastCandidateScore(BaseModel):
    model_name: str
    family: str
    primary_metric: str = "root_mean_squared_error"
    mean_score: float | None = None
    fit_seconds: float = 0
    status: Literal["completed", "failed"] = "completed"
    error: str | None = None
    failure_stage: str | None = None
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, MetricSummary] = Field(default_factory=dict)
    fold_scores: list[ForecastFoldScore] = Field(default_factory=list)
    supports_prediction_intervals: bool = False


class ForecastPoint(BaseModel):
    timestamp: str
    predicted: float
    lower_95: float | None = None
    upper_95: float | None = None


class ForecastResult(BaseModel):
    task: TaskDecision
    primary_metric: str
    selection_rule: str
    leaderboard: list[ForecastCandidateScore]
    winner: str | None
    contract: ForecastContract
    forecast: list[ForecastPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_strategy: str
    random_seed: int
    software_versions: dict[str, str] = Field(default_factory=dict)

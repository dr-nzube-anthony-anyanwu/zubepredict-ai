from __future__ import annotations

import importlib.util
import math
import platform
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans, MiniBatchKMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.mixture import GaussianMixture
from sklearn.neighbors import LocalOutlierFactor, NearestNeighbors
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from zubepredict_core.data_engine.quality_guardian import assess_data_quality
from zubepredict_core.ml_engine.tournament import TournamentCancelled
from zubepredict_core.shared.schemas import (
    SegmentDescription,
    TaskDecision,
    TaskType,
    UnsupervisedAssignment,
    UnsupervisedCandidateScore,
    UnsupervisedResult,
    UnsupervisedSuitability,
)

SEGMENT_CAVEAT = (
    "Descriptive pattern only; this algorithmic segment is not a verified real-world "
    "group, causal category, or ground truth."
)


@dataclass(frozen=True)
class _Candidate:
    name: str
    family: str
    parameters: dict[str, Any]
    factory: Callable[[int], Any]


@dataclass
class _Evaluation:
    score: UnsupervisedCandidateScore
    labels: np.ndarray[Any, Any] | None = None
    anomaly_scores: np.ndarray[Any, Any] | None = None


def _software_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for package in ("numpy", "pandas", "scikit-learn"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            continue
    return versions


def assess_unsupervised_suitability(
    df: pd.DataFrame,
    *,
    task_type: TaskType,
) -> UnsupervisedSuitability:
    if task_type not in {TaskType.CLUSTERING, TaskType.ANOMALY_DETECTION}:
        raise ValueError("Suitability is defined only for clustering and anomaly detection.")
    if len(set(map(str, df.columns))) != len(df.columns):
        return UnsupervisedSuitability(
            rows=len(df),
            original_columns=len(df.columns),
            can_run=False,
            blockers=["Dataset column names must be unique."],
        )

    quality = assess_data_quality(df)
    excluded = set(quality.suggested_exclusions)
    usable = [str(column) for column in df.columns if str(column) not in excluded]
    numeric = df[usable].select_dtypes(include="number").columns.astype(str).tolist()
    categorical = [column for column in usable if column not in numeric]
    estimated_encoded = len(numeric) + sum(
        min(int(df[column].nunique(dropna=True)), 50) for column in categorical
    )
    minimum_rows = 10 if task_type == TaskType.CLUSTERING else 20
    blockers: list[str] = []
    warnings = [finding.message for finding in quality.warnings]
    if len(df) < minimum_rows:
        blockers.append(f"{task_type.value} requires at least {minimum_rows} rows.")
    if not usable:
        blockers.append("No suitable numeric or categorical features remain after safety checks.")
    if estimated_encoded > 500:
        blockers.append(
            f"The usable categoricals expand to about {estimated_encoded} features; "
            "the safe cap is 500."
        )
    if len(df) * max(estimated_encoded, 1) > 10_000_000:
        blockers.append("The dense working matrix would exceed the Stage 8 memory budget.")
    if categorical and not numeric:
        warnings.append(
            "All usable features are categorical; distance-based structure depends "
            "on one-hot encoding."
        )
    warnings.append(
        "Unsupervised patterns are exploratory and must not be interpreted as verified labels."
    )
    return UnsupervisedSuitability(
        rows=len(df),
        original_columns=len(df.columns),
        usable_columns=usable,
        numeric_columns=numeric,
        categorical_columns=categorical,
        excluded_columns=sorted(excluded),
        estimated_encoded_features=estimated_encoded,
        can_run=not blockers,
        blockers=blockers,
        warnings=list(dict.fromkeys(warnings)),
    )


def _preprocessor(suitability: UnsupervisedSuitability) -> ColumnTransformer:
    numeric = Pipeline(
        [("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]
    )
    categorical = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "encoder",
                OneHotEncoder(
                    handle_unknown="ignore",
                    min_frequency=2,
                    max_categories=50,
                    sparse_output=False,
                ),
            ),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", numeric, suitability.numeric_columns),
            ("categorical", categorical, suitability.categorical_columns),
        ],
        remainder="drop",
    )


def _matrix(df: pd.DataFrame, suitability: UnsupervisedSuitability) -> np.ndarray[Any, Any]:
    cleaned = df[suitability.usable_columns].replace([np.inf, -np.inf], np.nan)
    transformed = _preprocessor(suitability).fit_transform(cleaned)
    matrix = np.asarray(transformed, dtype=float)
    if matrix.shape[1] == 0 or not np.isfinite(matrix).all():
        raise ValueError("Preprocessing produced no finite unsupervised features.")
    return matrix


def _cluster_count(labels: np.ndarray[Any, Any]) -> int:
    return len(set(labels.tolist()) - {-1})


def _cluster_metrics(
    matrix: np.ndarray[Any, Any], labels: np.ndarray[Any, Any], seed: int
) -> dict[str, float]:
    keep = labels != -1
    clusters = _cluster_count(labels)
    noise_fraction = float((labels == -1).mean())
    metrics = {"cluster_count": float(clusters), "noise_fraction": noise_fraction}
    if clusters < 2 or int(keep.sum()) <= clusters:
        raise ValueError("Candidate did not produce at least two evaluable clusters.")
    sample_size = min(2_000, int(keep.sum()))
    metrics.update(
        silhouette=float(
            silhouette_score(matrix[keep], labels[keep], sample_size=sample_size, random_state=seed)
        ),
        davies_bouldin=float(davies_bouldin_score(matrix[keep], labels[keep])),
        calinski_harabasz=float(calinski_harabasz_score(matrix[keep], labels[keep])),
    )
    return metrics


def _cluster_stability(
    df: pd.DataFrame,
    suitability: UnsupervisedSuitability,
    candidate: _Candidate,
    full_labels: np.ndarray[Any, Any],
    seed: int,
) -> list[float]:
    rng = np.random.default_rng(seed)
    scores: list[float] = []
    sample_size = max(8, int(len(df) * 0.8))
    for repeat in range(3):
        indices = np.sort(rng.choice(len(df), size=sample_size, replace=False))
        subset_matrix = _matrix(df.iloc[indices], suitability)
        labels = np.asarray(candidate.factory(seed + repeat + 1).fit_predict(subset_matrix))
        if _cluster_count(labels) < 2:
            scores.append(0.0)
        else:
            scores.append(float(adjusted_rand_score(full_labels[indices], labels)))
    return scores


def _dbscan_eps(matrix: np.ndarray[Any, Any]) -> float:
    neighbors = min(5, len(matrix) - 1)
    distances, _ = NearestNeighbors(n_neighbors=neighbors).fit(matrix).kneighbors(matrix)
    return max(float(np.quantile(distances[:, -1], 0.8)), 1e-6)


def _kmeans_factory(cluster_count: int) -> Callable[[int], KMeans]:
    def factory(seed: int) -> KMeans:
        return KMeans(n_clusters=cluster_count, n_init=10, random_state=seed)

    return factory


def _gmm_factory(component_count: int) -> Callable[[int], GaussianMixture]:
    def factory(seed: int) -> GaussianMixture:
        return GaussianMixture(
            n_components=component_count,
            covariance_type="full",
            random_state=seed,
        )

    return factory


def _clustering_candidates(matrix: np.ndarray[Any, Any], max_candidates: int) -> list[_Candidate]:
    upper_k = min(6, max(2, int(math.sqrt(len(matrix)))), len(matrix) - 1)
    k_values = list(range(2, upper_k + 1))
    eps = _dbscan_eps(matrix)
    candidates: list[_Candidate] = []
    for k in k_values:
        candidates.extend(
            [
                _Candidate(
                    f"K-Means (k={k})",
                    "kmeans",
                    {"n_clusters": k, "n_init": 10},
                    _kmeans_factory(k),
                ),
                _Candidate(
                    f"Gaussian Mixture (k={k})",
                    "gaussian_mixture",
                    {"n_components": k, "covariance_type": "full"},
                    _gmm_factory(k),
                ),
            ]
        )
    representative_k = k_values[min(1, len(k_values) - 1)]
    candidates.extend(
        [
            _Candidate(
                f"MiniBatch K-Means (k={representative_k})",
                "minibatch_kmeans",
                {"n_clusters": representative_k, "n_init": 10},
                lambda seed: MiniBatchKMeans(
                    n_clusters=representative_k,
                    n_init=10,
                    batch_size=min(256, len(matrix)),
                    random_state=seed,
                ),
            ),
            _Candidate(
                "DBSCAN",
                "dbscan",
                {"eps": eps, "min_samples": 5},
                lambda seed: DBSCAN(eps=eps, min_samples=5),
            ),
        ]
    )
    if importlib.util.find_spec("sklearn.cluster") is not None:
        try:
            from sklearn.cluster import HDBSCAN

            min_size = max(5, len(matrix) // 20)
            candidates.append(
                _Candidate(
                    "HDBSCAN",
                    "hdbscan",
                    {"min_cluster_size": min_size},
                    lambda seed: HDBSCAN(min_cluster_size=min_size, copy=False),
                )
            )
        except ImportError:
            pass
    if len(candidates) <= max_candidates:
        return candidates
    required = {"kmeans", "minibatch_kmeans", "gaussian_mixture", "dbscan", "hdbscan"}
    selected: list[_Candidate] = []
    for candidate in candidates:
        if candidate.family in required:
            selected.append(candidate)
            required.remove(candidate.family)
    for candidate in candidates:
        if candidate not in selected and len(selected) < max_candidates:
            selected.append(candidate)
    return selected[:max_candidates]


def _evaluate_cluster_candidate(
    df: pd.DataFrame,
    matrix: np.ndarray[Any, Any],
    suitability: UnsupervisedSuitability,
    candidate: _Candidate,
    seed: int,
) -> _Evaluation:
    started = time.perf_counter()
    try:
        estimator = candidate.factory(seed)
        labels = np.asarray(estimator.fit_predict(matrix))
        metrics = _cluster_metrics(matrix, labels, seed)
        if candidate.family == "gaussian_mixture":
            metrics["bic"] = float(estimator.bic(matrix))
            metrics["aic"] = float(estimator.aic(matrix))
        stability = _cluster_stability(df, suitability, candidate, labels, seed)
        mean_stability = float(np.mean(stability))
        metrics["mean_stability"] = mean_stability
        selection_score = (
            0.55 * ((metrics["silhouette"] + 1) / 2)
            + 0.35 * max(mean_stability, 0)
            + 0.10 * (1 - metrics["noise_fraction"])
        )
        return _Evaluation(
            score=UnsupervisedCandidateScore(
                model_name=candidate.name,
                family=candidate.family,
                primary_metric="stability_adjusted_internal_validity",
                selection_score=selection_score,
                fit_seconds=time.perf_counter() - started,
                hyperparameters=candidate.parameters,
                metrics=metrics,
                stability_scores=stability,
            ),
            labels=labels,
        )
    except Exception as exc:
        return _Evaluation(
            score=UnsupervisedCandidateScore(
                model_name=candidate.name,
                family=candidate.family,
                primary_metric="stability_adjusted_internal_validity",
                fit_seconds=time.perf_counter() - started,
                status="failed",
                error=str(exc)[:500],
                failure_stage="fit_or_internal_validation",
                hyperparameters=candidate.parameters,
            )
        )


def _top_anomaly_labels(scores: np.ndarray[Any, Any], contamination: float) -> np.ndarray[Any, Any]:
    count = max(1, int(math.ceil(len(scores) * contamination)))
    labels = np.ones(len(scores), dtype=int)
    labels[np.argsort(scores)[-count:]] = -1
    return labels


def _anomaly_output(
    family: str,
    matrix: np.ndarray[Any, Any],
    contamination: float,
    seed: int,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    if family == "robust_zscore":
        median = np.median(matrix, axis=0)
        mad = np.median(np.abs(matrix - median), axis=0)
        scale = np.where(mad > 1e-12, 1.4826 * mad, 1.0)
        scores = np.max(np.abs((matrix - median) / scale), axis=1)
        return _top_anomaly_labels(scores, contamination), scores
    if family == "isolation_forest":
        estimator = IsolationForest(contamination=contamination, random_state=seed, n_jobs=1)
        labels = estimator.fit_predict(matrix)
        return labels, -estimator.score_samples(matrix)
    neighbors = min(20, len(matrix) - 1)
    estimator = LocalOutlierFactor(n_neighbors=neighbors, contamination=contamination)
    labels = estimator.fit_predict(matrix)
    return labels, -estimator.negative_outlier_factor_


def _jaccard_anomalies(left: np.ndarray[Any, Any], right: np.ndarray[Any, Any]) -> float:
    left_set = set(np.flatnonzero(left == -1).tolist())
    right_set = set(np.flatnonzero(right == -1).tolist())
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 1.0


def _evaluate_anomaly_candidate(
    matrix: np.ndarray[Any, Any], family: str, contamination: float, seed: int
) -> _Evaluation:
    names = {
        "robust_zscore": "Robust Z-Score Baseline",
        "isolation_forest": "Isolation Forest",
        "local_outlier_factor": "Local Outlier Factor",
    }
    started = time.perf_counter()
    try:
        labels, scores = _anomaly_output(family, matrix, contamination, seed)
        rng = np.random.default_rng(seed)
        stability: list[float] = []
        scale = np.std(matrix, axis=0)
        for repeat in range(3):
            perturbed = matrix + rng.normal(0, 1e-4, matrix.shape) * np.where(scale > 0, scale, 1)
            repeated_labels, _ = _anomaly_output(
                family, perturbed, contamination, seed + repeat + 1
            )
            stability.append(_jaccard_anomalies(labels, repeated_labels))
        metrics = {
            "anomaly_fraction": float((labels == -1).mean()),
            "score_median": float(np.median(scores)),
            "score_interquartile_range": float(
                np.quantile(scores, 0.75) - np.quantile(scores, 0.25)
            ),
            "mean_stability": float(np.mean(stability)),
        }
        return _Evaluation(
            UnsupervisedCandidateScore(
                model_name=names[family],
                family=family,
                primary_metric="consensus_stability",
                fit_seconds=time.perf_counter() - started,
                hyperparameters={"contamination": contamination},
                metrics=metrics,
                stability_scores=stability,
            ),
            labels,
            scores,
        )
    except Exception as exc:
        return _Evaluation(
            UnsupervisedCandidateScore(
                model_name=names[family],
                family=family,
                primary_metric="consensus_stability",
                fit_seconds=time.perf_counter() - started,
                status="failed",
                error=str(exc)[:500],
                failure_stage="fit_or_stability",
                hyperparameters={"contamination": contamination},
            )
        )


def _segment_descriptions(
    df: pd.DataFrame,
    suitability: UnsupervisedSuitability,
    labels: np.ndarray[Any, Any],
) -> list[SegmentDescription]:
    descriptions: list[SegmentDescription] = []
    for label in sorted(set(labels.tolist()) - {-1}):
        mask = labels == label
        facts: list[tuple[float, str]] = []
        for column in suitability.numeric_columns:
            overall = pd.to_numeric(df[column], errors="coerce")
            segment = overall[mask]
            scale = float(overall.std())
            difference = abs(float(segment.median()) - float(overall.median())) / max(scale, 1e-12)
            facts.append(
                (
                    difference,
                    f"{column}: median {segment.median():.4g} versus "
                    f"{overall.median():.4g} overall",
                )
            )
        for column in suitability.categorical_columns:
            segment = df.loc[mask, column].dropna().astype(str)
            if segment.empty:
                continue
            mode = str(segment.mode().iloc[0])
            segment_rate = float((segment == mode).mean())
            overall_rate = float((df[column].dropna().astype(str) == mode).mean())
            facts.append(
                (
                    abs(segment_rate - overall_rate),
                    f"{column}: '{mode}' appears in {segment_rate:.1%} versus "
                    f"{overall_rate:.1%} overall",
                )
            )
        descriptions.append(
            SegmentDescription(
                segment_label=int(label),
                size=int(mask.sum()),
                fraction=float(mask.mean()),
                distinguishing_features=[fact for _, fact in sorted(facts, reverse=True)[:3]],
                caveat=SEGMENT_CAVEAT,
            )
        )
    return descriptions


def run_unsupervised_tournament(
    df: pd.DataFrame,
    decision: TaskDecision,
    *,
    seed: int = 42,
    max_candidates: int = 12,
    contamination: float = 0.05,
    compute_budget_seconds: int = 600,
    progress_callback: Callable[[int, str], None] | None = None,
    cancellation_check: Callable[[], bool] | None = None,
) -> UnsupervisedResult:
    if decision.task_type not in {TaskType.CLUSTERING, TaskType.ANOMALY_DETECTION}:
        raise ValueError("The unsupervised tournament supports clustering and anomaly detection.")
    if not 0 < contamination <= 0.25:
        raise ValueError("Anomaly contamination must be greater than 0 and at most 0.25.")
    suitability = assess_unsupervised_suitability(df, task_type=decision.task_type)
    if not suitability.can_run:
        raise ValueError(
            "Unsupervised suitability checks failed: " + "; ".join(suitability.blockers)
        )
    matrix = _matrix(df, suitability)
    started = time.perf_counter()
    evaluations: list[_Evaluation] = []

    if decision.task_type == TaskType.CLUSTERING:
        candidates = _clustering_candidates(matrix, max(max_candidates, 5))
        for index, candidate in enumerate(candidates):
            if cancellation_check is not None and cancellation_check():
                raise TournamentCancelled("Experiment cancellation was requested.")
            if time.perf_counter() - started >= compute_budget_seconds:
                evaluations.append(
                    _Evaluation(
                        UnsupervisedCandidateScore(
                            model_name=candidate.name,
                            family=candidate.family,
                            primary_metric="stability_adjusted_internal_validity",
                            status="failed",
                            error="The compute budget was exhausted before evaluation.",
                            failure_stage="resource_budget",
                            hyperparameters=candidate.parameters,
                        )
                    )
                )
                continue
            if progress_callback is not None:
                progress_callback(25 + int(index / len(candidates) * 60), candidate.name)
            evaluations.append(
                _evaluate_cluster_candidate(df, matrix, suitability, candidate, seed)
            )
        primary_metric = "stability_adjusted_internal_validity"
        selection_rule = (
            "Highest weighted combination of silhouette (55%), resampling ARI stability "
            "(35%), and non-noise coverage (10%); internal evidence only."
        )
    else:
        families = ("robust_zscore", "isolation_forest", "local_outlier_factor")
        for index, family in enumerate(families):
            if cancellation_check is not None and cancellation_check():
                raise TournamentCancelled("Experiment cancellation was requested.")
            if progress_callback is not None:
                progress_callback(25 + index * 20, family.replace("_", " ").title())
            evaluations.append(_evaluate_anomaly_candidate(matrix, family, contamination, seed))
        successful = [item for item in evaluations if item.labels is not None]
        for evaluation in successful:
            assert evaluation.labels is not None
            peers = [
                _jaccard_anomalies(evaluation.labels, peer.labels)
                for peer in successful
                if peer is not evaluation and peer.labels is not None
            ]
            consensus = float(np.mean(peers)) if peers else 0.0
            evaluation.score.metrics["mean_consensus_jaccard"] = consensus
            evaluation.score.selection_score = (
                0.6 * evaluation.score.metrics["mean_stability"] + 0.4 * consensus
            )
        primary_metric = "consensus_stability"
        selection_rule = (
            "Highest weighted perturbation stability (60%) and cross-detector anomaly-set "
            "agreement (40%); no ground-truth accuracy is implied."
        )

    successful = [
        item
        for item in evaluations
        if item.score.status == "completed" and item.score.selection_score is not None
    ]
    successful.sort(key=lambda item: item.score.selection_score or -math.inf, reverse=True)
    failed = [item for item in evaluations if item not in successful]
    ordered = [*successful, *failed]
    winner = successful[0] if successful else None
    assignments: list[UnsupervisedAssignment] = []
    if winner is not None and winner.labels is not None:
        for position, index in enumerate(df.index):
            label = int(winner.labels[position])
            assignments.append(
                UnsupervisedAssignment(
                    row_index=str(index),
                    label=label,
                    anomaly=label == -1 and decision.task_type == TaskType.ANOMALY_DETECTION,
                    anomaly_score=(
                        float(winner.anomaly_scores[position])
                        if winner.anomaly_scores is not None
                        else None
                    ),
                )
            )
    descriptions = (
        _segment_descriptions(df, suitability, winner.labels)
        if winner is not None
        and winner.labels is not None
        and decision.task_type == TaskType.CLUSTERING
        else []
    )
    warnings = list(suitability.warnings)
    if winner is None:
        warnings.append("Every unsupervised candidate failed; no pattern was selected.")
    return UnsupervisedResult(
        task=decision,
        primary_metric=primary_metric,
        selection_rule=selection_rule,
        leaderboard=[item.score for item in ordered],
        winner=winner.score.model_name if winner else None,
        suitability=suitability,
        assignments=assignments,
        segment_descriptions=descriptions,
        warnings=warnings,
        validation_strategy=(
            "Three 80% row-subsample refits scored by adjusted Rand agreement"
            if decision.task_type == TaskType.CLUSTERING
            else "Three deterministic small-perturbation refits plus detector-consensus Jaccard"
        ),
        random_seed=seed,
        software_versions=_software_versions(),
    )

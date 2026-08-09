from pathlib import Path

import pandas as pd

SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls", ".parquet"}


def load_dataframe(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported file type: {suffix}. Use CSV, Excel, or Parquet.")
    try:
        if suffix == ".csv":
            return pd.read_csv(file_path)
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(file_path)
        return pd.read_parquet(file_path)
    except pd.errors.EmptyDataError as exc:
        raise ValueError("The dataset is empty.") from exc


def validate_dimensions(df: pd.DataFrame, max_rows: int, max_columns: int) -> None:
    if df.empty:
        raise ValueError("The dataset is empty.")
    if len(df) > max_rows:
        raise ValueError(f"Dataset has {len(df):,} rows; the current limit is {max_rows:,}.")
    if len(df.columns) > max_columns:
        raise ValueError(
            f"Dataset has {len(df.columns):,} columns; the current limit is {max_columns:,}."
        )

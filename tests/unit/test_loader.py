import pandas as pd
import pytest
from zubepredict_core.data_engine.loader import load_dataframe, validate_dimensions


def test_rejects_unsupported_file_type(tmp_path) -> None:
    path = tmp_path / "dataset.txt"
    path.write_text("value\n1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        load_dataframe(path)


def test_rejects_empty_csv(tmp_path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="dataset is empty"):
        load_dataframe(path)


def test_rejects_empty_dataframe() -> None:
    with pytest.raises(ValueError, match="dataset is empty"):
        validate_dimensions(pd.DataFrame(), max_rows=10, max_columns=10)


@pytest.mark.parametrize(
    ("dataframe", "message"),
    [
        (pd.DataFrame({"value": [1, 2, 3]}), "3 rows"),
        (pd.DataFrame([[1, 2, 3]], columns=["a", "b", "c"]), "3 columns"),
    ],
)
def test_rejects_oversized_dimensions(dataframe: pd.DataFrame, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_dimensions(dataframe, max_rows=2, max_columns=2)

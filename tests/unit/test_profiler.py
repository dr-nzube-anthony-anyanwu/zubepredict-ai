import pandas as pd
from zubepredict_core.data_engine.profiler import profile_dataframe


def test_profiler_detects_duplicates_and_identifier() -> None:
    df = pd.DataFrame({"patient_id": ["a", "b", "b"], "outcome": [1, 0, 0]})
    result = profile_dataframe(df)
    assert result.rows == 3
    assert result.duplicate_rows == 1
    assert result.column_profiles[0].suspected_identifier
    assert "outcome" in result.possible_targets
    assert result.quality_report is not None
    assert "duplicate_rows" in {item.code for item in result.quality_report.findings}

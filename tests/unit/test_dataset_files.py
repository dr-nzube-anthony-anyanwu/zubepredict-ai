from io import BytesIO

import pandas as pd
import pytest
from zubepredict_core.datasets.files import (
    DatasetFileError,
    DatasetFileFormat,
    inspect_dataset,
    stream_to_file,
    validate_file_signature,
    validate_upload_metadata,
)


def test_upload_metadata_requires_matching_extension_and_media_type() -> None:
    metadata = validate_upload_metadata(r"C:\fakepath\sales.CSV", "text/csv; charset=utf-8")

    assert metadata.original_filename == "sales.CSV"
    assert metadata.file_format == DatasetFileFormat.CSV

    with pytest.raises(DatasetFileError, match="does not match"):
        validate_upload_metadata("sales.csv", "application/pdf")


def test_stream_to_file_hashes_chunks_and_stops_at_limit() -> None:
    destination = BytesIO()
    result = stream_to_file([b"a,b\n", b"1,2\n"], destination, max_bytes=8)

    assert result.size_bytes == 8
    assert len(result.sha256) == 64

    with pytest.raises(DatasetFileError, match="upload limit"):
        stream_to_file([b"1234", b"5"], BytesIO(), max_bytes=4)


def test_csv_signature_rejects_disguised_binary(tmp_path) -> None:
    path = tmp_path / "fake.csv"
    path.write_bytes(b"PK\x03\x04not-really-csv")

    with pytest.raises(DatasetFileError, match="binary file signature"):
        validate_file_signature(
            path,
            DatasetFileFormat.CSV,
            max_uncompressed_bytes=1_000_000,
        )


def test_excel_and_parquet_signatures_match_extensions(tmp_path) -> None:
    frame = pd.DataFrame({"value": [1, 2]})
    excel = tmp_path / "values.xlsx"
    parquet = tmp_path / "values.parquet"
    frame.to_excel(excel, index=False)
    frame.to_parquet(parquet, index=False)

    validate_file_signature(
        excel,
        DatasetFileFormat.XLSX,
        max_uncompressed_bytes=5_000_000,
    )
    validate_file_signature(
        parquet,
        DatasetFileFormat.PARQUET,
        max_uncompressed_bytes=5_000_000,
    )

    corrupted = tmp_path / "corrupted.parquet"
    corrupted.write_bytes(b"PAR1missing-footer")
    with pytest.raises(DatasetFileError, match="signature"):
        validate_file_signature(
            corrupted,
            DatasetFileFormat.PARQUET,
            max_uncompressed_bytes=5_000_000,
        )


@pytest.mark.parametrize("file_format", [DatasetFileFormat.CSV, DatasetFileFormat.XLSX])
def test_preview_is_capped_without_losing_total_dimensions(tmp_path, file_format) -> None:
    frame = pd.DataFrame({f"column_{number}": range(5) for number in range(4)})
    suffix = ".csv" if file_format == DatasetFileFormat.CSV else ".xlsx"
    path = tmp_path / f"dataset{suffix}"
    if file_format == DatasetFileFormat.CSV:
        frame.to_csv(path, index=False)
    else:
        frame.to_excel(path, index=False)

    inspection = inspect_dataset(
        path,
        file_format,
        max_rows=10,
        max_columns=10,
        preview_rows=2,
        preview_columns=2,
    )

    assert inspection.row_count == 5
    assert inspection.column_count == 4
    assert inspection.column_names == [f"column_{number}" for number in range(4)]
    assert len(inspection.preview.rows) == 2
    assert len(inspection.preview.columns) == 2
    assert inspection.preview.rows_truncated is True
    assert inspection.preview.columns_truncated is True


def test_inspection_rejects_row_and_column_overflow(tmp_path) -> None:
    path = tmp_path / "wide.csv"
    pd.DataFrame({"a": [1, 2, 3], "b": [1, 2, 3]}).to_csv(path, index=False)

    with pytest.raises(DatasetFileError, match="row limit"):
        inspect_dataset(
            path,
            DatasetFileFormat.CSV,
            max_rows=2,
            max_columns=5,
            preview_rows=1,
            preview_columns=1,
        )

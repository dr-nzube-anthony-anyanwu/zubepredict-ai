from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, cast
from zipfile import BadZipFile, ZipFile

import pandas as pd
import pyarrow.parquet as parquet

STREAM_CHUNK_BYTES = 64 * 1024
XLS_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


class DatasetFileError(ValueError):
    """Raised when an uploaded dataset is unsafe or unsupported."""


class DatasetFileFormat(StrEnum):
    CSV = "csv"
    XLS = "xls"
    XLSX = "xlsx"
    PARQUET = "parquet"


@dataclass(frozen=True)
class UploadMetadata:
    original_filename: str
    media_type: str
    file_format: DatasetFileFormat
    suffix: str


@dataclass(frozen=True)
class StreamedFile:
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class DatasetPreview:
    columns: list[str]
    rows: list[dict[str, object]]
    rows_truncated: bool
    columns_truncated: bool


@dataclass(frozen=True)
class DatasetInspection:
    row_count: int
    column_count: int
    column_names: list[str]
    preview: DatasetPreview


_FORMAT_BY_SUFFIX = {
    ".csv": DatasetFileFormat.CSV,
    ".xls": DatasetFileFormat.XLS,
    ".xlsx": DatasetFileFormat.XLSX,
    ".parquet": DatasetFileFormat.PARQUET,
}

_MEDIA_TYPES = {
    DatasetFileFormat.CSV: {
        "text/csv",
        "application/csv",
        "text/plain",
        "application/vnd.ms-excel",
        "application/octet-stream",
    },
    DatasetFileFormat.XLS: {
        "application/vnd.ms-excel",
        "application/octet-stream",
    },
    DatasetFileFormat.XLSX: {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
    },
    DatasetFileFormat.PARQUET: {
        "application/vnd.apache.parquet",
        "application/x-parquet",
        "application/octet-stream",
    },
}


def validate_upload_metadata(filename: str, content_type: str) -> UploadMetadata:
    cleaned = filename.replace("\\", "/").split("/")[-1].strip()
    if not cleaned or len(cleaned) > 255 or any(ord(character) < 32 for character in cleaned):
        raise DatasetFileError("The dataset filename is invalid.")
    suffix = Path(cleaned).suffix.lower()
    file_format = _FORMAT_BY_SUFFIX.get(suffix)
    if file_format is None:
        raise DatasetFileError("Unsupported file type. Use CSV, Excel, or Parquet.")

    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type not in _MEDIA_TYPES[file_format]:
        raise DatasetFileError(
            f"Content type '{media_type or 'missing'}' does not match the {suffix} extension."
        )
    return UploadMetadata(cleaned, media_type, file_format, suffix)


def stream_to_file(chunks: Iterable[bytes], destination: BinaryIO, max_bytes: int) -> StreamedFile:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive.")
    digest = sha256()
    total = 0
    for chunk in chunks:
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise DatasetFileError(f"File exceeds the {max_bytes} byte upload limit.")
        destination.write(chunk)
        digest.update(chunk)
    if total == 0:
        raise DatasetFileError("The dataset is empty.")
    destination.flush()
    return StreamedFile(size_bytes=total, sha256=digest.hexdigest())


def _validate_xlsx_archive(path: Path, max_uncompressed_bytes: int) -> None:
    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise DatasetFileError("The .xlsx file is not a valid Excel workbook.")
            total = 0
            for member in archive.infolist():
                total += member.file_size
                if total > max_uncompressed_bytes:
                    raise DatasetFileError("The Excel workbook expands beyond the safe limit.")
                if member.file_size > 1_000_000 and member.compress_size:
                    if member.file_size / member.compress_size > 100:
                        raise DatasetFileError(
                            "The Excel workbook has an unsafe compression ratio."
                        )
    except BadZipFile as exc:
        raise DatasetFileError("The .xlsx file signature is invalid.") from exc


def validate_file_signature(
    path: str | Path,
    file_format: DatasetFileFormat,
    *,
    max_uncompressed_bytes: int,
) -> None:
    file_path = Path(path)
    with file_path.open("rb") as source:
        head = source.read(8192)
        source.seek(max(file_path.stat().st_size - 4, 0))
        tail = source.read(4)

    if file_format == DatasetFileFormat.CSV:
        if b"\x00" in head or head.startswith((*ZIP_SIGNATURES, XLS_SIGNATURE, b"PAR1")):
            raise DatasetFileError("The .csv file contains a binary file signature.")
        try:
            head.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DatasetFileError("CSV datasets must use UTF-8 text encoding.") from exc
        return
    if file_format == DatasetFileFormat.XLS:
        if not head.startswith(XLS_SIGNATURE):
            raise DatasetFileError("The .xls file signature is invalid.")
        return
    if file_format == DatasetFileFormat.XLSX:
        if not head.startswith(ZIP_SIGNATURES):
            raise DatasetFileError("The .xlsx file signature is invalid.")
        _validate_xlsx_archive(file_path, max_uncompressed_bytes)
        return
    if not head.startswith(b"PAR1") or tail != b"PAR1":
        raise DatasetFileError("The .parquet file signature is invalid.")


def _json_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    return cast(
        list[dict[str, object]], json.loads(frame.to_json(orient="records", date_format="iso"))
    )


def inspect_dataset(
    path: str | Path,
    file_format: DatasetFileFormat,
    *,
    max_rows: int,
    max_columns: int,
    preview_rows: int,
    preview_columns: int,
) -> DatasetInspection:
    file_path = Path(path)
    try:
        if file_format == DatasetFileFormat.CSV:
            frame = pd.read_csv(file_path, nrows=max_rows + 1)
        elif file_format in {DatasetFileFormat.XLS, DatasetFileFormat.XLSX}:
            frame = pd.read_excel(file_path, nrows=max_rows + 1)
        else:
            source = parquet.ParquetFile(file_path)
            row_count = source.metadata.num_rows
            column_names = source.schema_arrow.names
            _validate_dimensions(row_count, len(column_names), max_rows, max_columns)
            selected = column_names[:preview_columns]
            batches = source.iter_batches(batch_size=preview_rows, columns=selected)
            first_batch = next(batches, None)
            preview_frame = first_batch.to_pandas() if first_batch is not None else pd.DataFrame()
            return DatasetInspection(
                row_count=row_count,
                column_count=len(column_names),
                column_names=[str(column) for column in column_names],
                preview=DatasetPreview(
                    columns=[str(column) for column in selected],
                    rows=_json_rows(preview_frame),
                    rows_truncated=row_count > preview_rows,
                    columns_truncated=len(column_names) > preview_columns,
                ),
            )
    except DatasetFileError:
        raise
    except pd.errors.EmptyDataError as exc:
        raise DatasetFileError("The dataset is empty.") from exc
    except Exception as exc:
        raise DatasetFileError(f"The {file_format.value} dataset could not be parsed.") from exc

    _validate_dimensions(len(frame), len(frame.columns), max_rows, max_columns)
    preview_frame = frame.iloc[:preview_rows, :preview_columns].copy()
    preview_frame.columns = [str(column) for column in preview_frame.columns]
    return DatasetInspection(
        row_count=len(frame),
        column_count=len(frame.columns),
        column_names=[str(column) for column in frame.columns],
        preview=DatasetPreview(
            columns=[str(column) for column in frame.columns[:preview_columns]],
            rows=_json_rows(preview_frame),
            rows_truncated=len(frame) > preview_rows,
            columns_truncated=len(frame.columns) > preview_columns,
        ),
    )


def _validate_dimensions(rows: int, columns: int, max_rows: int, max_columns: int) -> None:
    if rows == 0 or columns == 0:
        raise DatasetFileError("The dataset is empty.")
    if rows > max_rows:
        raise DatasetFileError(f"Dataset has more than the {max_rows:,} row limit.")
    if columns > max_columns:
        raise DatasetFileError(f"Dataset has {columns:,} columns; the limit is {max_columns:,}.")

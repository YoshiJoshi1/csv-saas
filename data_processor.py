from __future__ import annotations

import io
import os

import pandas as pd


def clean_uploaded_csv(uploaded_file) -> pd.DataFrame:
    """Convert an uploaded CSV file to a cleaned DataFrame."""
    file_name = str(getattr(uploaded_file, "name", "")).lower()
    if not file_name.endswith(".csv"):
        raise ValueError("Only .csv uploads are supported.")

    content_type = str(getattr(uploaded_file, "type", "")).lower()
    if content_type and "csv" not in content_type and "text/plain" not in content_type:
        raise ValueError("Invalid file type. Please upload a CSV file.")

    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "10"))
    max_rows = int(os.getenv("MAX_UPLOAD_ROWS", "250000"))
    max_columns = int(os.getenv("MAX_UPLOAD_COLUMNS", "200"))
    uploaded_file.seek(0, io.SEEK_END)
    file_size_bytes = uploaded_file.tell()
    uploaded_file.seek(0)
    if file_size_bytes > max_upload_mb * 1024 * 1024:
        raise ValueError(f"Uploaded file is too large. Max size is {max_upload_mb} MB.")

    try:
        df = pd.read_csv(uploaded_file)
    except pd.errors.ParserError as error:
        raise ValueError("CSV parsing failed. Please verify delimiter/format.") from error

    # Standardize column headers by removing extra whitespace.
    df.columns = df.columns.str.strip()
    if len(df.columns) > max_columns:
        raise ValueError(f"Too many columns. Max allowed is {max_columns}.")
    if len(df) > max_rows:
        raise ValueError(f"Too many rows. Max allowed is {max_rows}.")

    # Treat empty strings as missing values, then drop rows with missing values.
    df = df.replace(r"^\s*$", pd.NA, regex=True)
    df = df.dropna()

    # Standardize date columns to YYYY-MM-DD for common date-like headers.
    date_like_columns = [col for col in df.columns if "date" in col.lower()]
    for col in date_like_columns:
        parsed = pd.to_datetime(df[col], errors="coerce")
        df[col] = parsed.dt.strftime("%Y-%m-%d")
        df = df[df[col].notna()]

    return df.reset_index(drop=True)

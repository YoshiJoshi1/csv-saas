from __future__ import annotations

from typing import List, Tuple

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure


def _find_column(columns: List[str], keywords: List[str]) -> str | None:
    lowered = {col: col.lower() for col in columns}
    for keyword in keywords:
        for original, lower_col in lowered.items():
            if keyword in lower_col:
                return original
    return None


def generate_report_charts(cleaned_df: pd.DataFrame) -> Tuple[List[Tuple[str, Figure]], List[str]]:
    """Generate report charts from a cleaned DataFrame.

    Returns:
        (charts, messages)
        charts: list of (title, matplotlib_figure)
        messages: warning/info messages about missing/assumed columns
    """
    charts: List[Tuple[str, Figure]] = []
    messages: List[str] = []

    if cleaned_df.empty:
        return charts, ["The cleaned DataFrame is empty. No charts were generated."]

    columns = cleaned_df.columns.tolist()

    # 1) Time-series line chart of revenue
    date_col = _find_column(columns, ["date"])
    revenue_col = _find_column(columns, ["revenue", "sales", "amount", "total"])

    if date_col and revenue_col:
        ts_df = cleaned_df[[date_col, revenue_col]].copy()
        ts_df[date_col] = pd.to_datetime(ts_df[date_col], errors="coerce")
        ts_df[revenue_col] = pd.to_numeric(ts_df[revenue_col], errors="coerce")
        ts_df = ts_df.dropna().sort_values(date_col)

        if not ts_df.empty:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(ts_df[date_col], ts_df[revenue_col], marker="o")
            ax.set_title("Revenue Over Time")
            ax.set_xlabel("Date")
            ax.set_ylabel("Revenue")
            ax.grid(alpha=0.3)
            fig.autofmt_xdate()
            charts.append(("Time-Series: Revenue", fig))
        else:
            messages.append("Revenue time-series could not be generated after parsing date/revenue values.")
    else:
        messages.append("Skipped revenue time-series chart. Expected columns similar to 'date' and 'revenue'.")

    # 2) Bar chart of top 5 categories
    category_col = _find_column(columns, ["category", "segment", "type", "group"])
    if category_col:
        top_categories = cleaned_df[category_col].astype(str).value_counts().head(5)
        if not top_categories.empty:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.bar(top_categories.index, top_categories.values)
            ax.set_title("Top 5 Categories")
            ax.set_xlabel("Category")
            ax.set_ylabel("Count")
            ax.tick_params(axis="x", rotation=25)
            charts.append(("Top 5 Categories", fig))
    else:
        messages.append("Skipped top categories chart. Expected a column similar to 'category'.")

    # 3) Scatter plot for outlier identification
    numeric_cols = cleaned_df.select_dtypes(include="number").columns.tolist()
    x_col = revenue_col if revenue_col in numeric_cols else (numeric_cols[0] if numeric_cols else None)
    y_col = None
    if len(numeric_cols) >= 2:
        for col in numeric_cols:
            if col != x_col:
                y_col = col
                break

    if x_col and y_col:
        scatter_df = cleaned_df[[x_col, y_col]].copy()
        scatter_df[x_col] = pd.to_numeric(scatter_df[x_col], errors="coerce")
        scatter_df[y_col] = pd.to_numeric(scatter_df[y_col], errors="coerce")
        scatter_df = scatter_df.dropna()

        if not scatter_df.empty:
            # Simple IQR-based outlier flag on y-axis.
            q1 = scatter_df[y_col].quantile(0.25)
            q3 = scatter_df[y_col].quantile(0.75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            is_outlier = (scatter_df[y_col] < lower_bound) | (scatter_df[y_col] > upper_bound)

            fig, ax = plt.subplots(figsize=(8, 5))
            ax.scatter(
                scatter_df.loc[~is_outlier, x_col],
                scatter_df.loc[~is_outlier, y_col],
                alpha=0.6,
                label="Inlier",
            )
            ax.scatter(
                scatter_df.loc[is_outlier, x_col],
                scatter_df.loc[is_outlier, y_col],
                alpha=0.8,
                color="red",
                label="Outlier",
            )
            ax.set_title("Scatter Plot with Outliers Highlighted")
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            ax.legend()
            ax.grid(alpha=0.3)
            charts.append(("Outlier Scatter Plot", fig))
        else:
            messages.append("Scatter plot could not be generated after numeric conversion.")
    else:
        messages.append("Skipped outlier scatter chart. Expected at least two numeric columns.")

    return charts, messages

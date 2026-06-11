"""Streamlit frontend for the Universal Data Assistant.

This client is fully decoupled from the backend: it communicates only over
HTTP using the configurable ``BACKEND_URL``. That keeps a future React rewrite
a drop-in replacement.

Run with:
    streamlit run frontend/app.py
"""

from __future__ import annotations

import os
from typing import Any

import plotly.graph_objects as go
import requests
import streamlit as st

BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
API_BASE: str = f"{BACKEND_URL}/api/v1"
REQUEST_TIMEOUT_SECONDS: int = 120

CSV_EXTENSIONS: tuple[str, ...] = (".csv",)
EXCEL_EXTENSIONS: tuple[str, ...] = (".xlsx", ".xls")


def _extract_error_detail(response: requests.Response) -> str:
    """Pull a human-readable message out of an error response."""
    try:
        payload = response.json()
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        return str(detail)
    except ValueError:
        return response.text or f"Request failed with status {response.status_code}."


def upload_dataset(filename: str, data: bytes, content_type: str) -> dict[str, Any] | None:
    """Send a file to the correct upload endpoint based on its extension."""
    lowered = filename.lower()
    if lowered.endswith(CSV_EXTENSIONS):
        endpoint = f"{API_BASE}/datasets/upload/csv"
    elif lowered.endswith(EXCEL_EXTENSIONS):
        endpoint = f"{API_BASE}/datasets/upload/excel"
    else:
        st.error("Unsupported file type. Please upload a .csv, .xlsx or .xls file.")
        return None

    try:
        response = requests.post(
            endpoint,
            files={"file": (filename, data, content_type)},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        st.error(f"Could not reach the backend at {BACKEND_URL}: {exc}")
        return None

    if response.status_code == 201:
        return response.json()

    st.error(_extract_error_detail(response))
    return None


def fetch_datasets() -> list[dict[str, Any]]:
    """Retrieve the list of stored datasets from the backend."""
    try:
        response = requests.get(
            f"{API_BASE}/datasets", timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        st.error(f"Could not reach the backend at {BACKEND_URL}: {exc}")
        return []

    if response.status_code != 200:
        st.error(_extract_error_detail(response))
        return []

    return response.json().get("datasets", [])


def fetch_preview(dataset_id: str, limit: int = 10) -> dict[str, Any] | None:
    """Retrieve a preview of a single dataset from the backend."""
    try:
        response = requests.get(
            f"{API_BASE}/datasets/{dataset_id}/preview",
            params={"limit": limit},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        st.error(f"Could not reach the backend at {BACKEND_URL}: {exc}")
        return None

    if response.status_code != 200:
        st.error(_extract_error_detail(response))
        return None

    return response.json()


def render_preview(preview: dict[str, Any]) -> None:
    """Render a dataset preview: summary, data types and first rows."""
    st.markdown(f"#### Preview — {preview['filename']}")

    summary_cols = st.columns(3)
    summary_cols[0].metric("Rows", preview["rows"])
    summary_cols[1].metric("Columns", preview["columns"])
    summary_cols[2].metric("Type", preview["file_type"])

    st.markdown("**Data types**")
    st.dataframe(
        [
            {"Column": column, "Type": dtype}
            for column, dtype in preview["data_types"].items()
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown(f"**First {preview['preview_row_count']} row(s)**")
    if preview["preview_rows"]:
        st.dataframe(
            preview["preview_rows"],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("This dataset has no rows.")


def post_chart(dataset_id: str, question: str) -> dict[str, Any] | None:
    """Send a question to the visualization endpoint (answer + table + chart)."""
    try:
        response = requests.post(
            f"{API_BASE}/chart",
            json={"dataset_id": dataset_id, "question": question},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        st.error(f"Could not reach the backend at {BACKEND_URL}: {exc}")
        return None

    if response.status_code != 200:
        st.error(_extract_error_detail(response))
        return None

    return response.json()


def render_ask_tab() -> None:
    """Render the natural-language analytics interface."""
    st.subheader("Ask a question about your data")

    datasets = fetch_datasets()
    if not datasets:
        st.info("Upload a dataset first, then ask questions here.")
        return

    options = {
        f"{item['filename']}  ·  {item['rows']}×{item['columns']}": item["id"]
        for item in datasets
    }
    selected_label = st.selectbox("Dataset", list(options.keys()), key="ask_ds")
    question = st.text_input(
        "Your question",
        placeholder="e.g. What is the average age? / Top 5 products by sales",
        key="ask_q",
    )

    if st.button("Ask", type="primary", key="ask_btn"):
        if not question.strip():
            st.warning("Please enter a question.")
            return
        with st.spinner("Thinking…"):
            result = post_chart(options[selected_label], question.strip())
        if result is not None:
            _render_chart_result(result)


def _render_chart_result(result: dict[str, Any]) -> None:
    """Render the answer, data table and Plotly chart from a /chart response."""
    st.markdown("#### Answer")
    st.text(result["answer"])

    table_data = result.get("table_data")
    if table_data:
        st.markdown("#### Table")
        st.dataframe(table_data, use_container_width=True, hide_index=True)

    chart_spec = result.get("chart_spec")
    if chart_spec:
        st.markdown(f"#### Chart ({result.get('chart_type', '')})")
        st.plotly_chart(go.Figure(chart_spec), use_container_width=True)

    timing_cols = st.columns(2)
    timing_cols[0].metric(
        "Pandas execution", f"{result['execution_time_ms']:.2f} ms"
    )
    timing_cols[1].metric(
        "Total (incl. LLM)", f"{result['total_time_ms']:.2f} ms"
    )


def post_report(dataset_id: str, questions: list[str]) -> dict[str, Any] | None:
    """Request report generation; returns the report metadata."""
    try:
        response = requests.post(
            f"{API_BASE}/reports",
            json={"dataset_id": dataset_id, "questions": questions},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        st.error(f"Could not reach the backend at {BACKEND_URL}: {exc}")
        return None

    if response.status_code != 201:
        st.error(_extract_error_detail(response))
        return None

    return response.json()


def fetch_report_pdf(report_id: str) -> bytes | None:
    """Download the generated PDF bytes for a report."""
    try:
        response = requests.get(
            f"{API_BASE}/reports/{report_id}/download",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        st.error(f"Could not reach the backend at {BACKEND_URL}: {exc}")
        return None

    if response.status_code != 200:
        st.error(_extract_error_detail(response))
        return None

    return response.content


def _api_get(path: str) -> Any | None:
    """GET a JSON endpoint, surfacing errors in the UI."""
    try:
        response = requests.get(f"{API_BASE}{path}", timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        st.error(f"Could not reach the backend at {BACKEND_URL}: {exc}")
        return None
    if response.status_code != 200:
        st.error(_extract_error_detail(response))
        return None
    return response.json()


def _api_post(path: str, payload: dict[str, Any], ok: int = 200) -> Any | None:
    """POST JSON to an endpoint, surfacing errors in the UI."""
    try:
        response = requests.post(
            f"{API_BASE}{path}", json=payload, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        st.error(f"Could not reach the backend at {BACKEND_URL}: {exc}")
        return None
    if response.status_code != ok:
        st.error(_extract_error_detail(response))
        return None
    return response.json()


def render_connect_tab() -> None:
    """Render the database connection + table-registration interface."""
    st.subheader("Connect a database")

    with st.expander("Add a connection", expanded=True):
        name = st.text_input("Connection name", key="conn_name")
        db_type = st.selectbox(
            "Database type", ["sqlite", "postgresql", "mysql"], key="conn_type"
        )
        payload: dict[str, Any] = {"name": name, "db_type": db_type}
        if db_type == "sqlite":
            payload["database"] = st.text_input(
                "SQLite file path", key="conn_sqlite_path"
            )
        else:
            cols = st.columns(2)
            payload["host"] = cols[0].text_input("Host", key="conn_host")
            payload["port"] = cols[1].number_input(
                "Port", min_value=1, max_value=65535, value=5432, key="conn_port"
            )
            payload["database"] = st.text_input("Database name", key="conn_db")
            payload["username"] = st.text_input("Username", key="conn_user")
            payload["password"] = st.text_input(
                "Password", type="password", key="conn_pwd"
            )

        if st.button("Save connection", type="primary", key="conn_save"):
            if not name:
                st.warning("Please enter a connection name.")
            else:
                created = _api_post("/connections", payload, ok=201)
                if created is not None:
                    st.success(f"Saved connection '{created['name']}'.")

    st.divider()
    st.markdown("### Connections")
    conns = _api_get("/connections") or []
    if not conns:
        st.info("No connections yet.")
        return

    labels = {f"{c['name']} ({c['db_type']})": c["id"] for c in conns}
    selected = st.selectbox("Select a connection", list(labels.keys()), key="conn_select")
    conn_id = labels[selected]

    action_cols = st.columns(2)
    if action_cols[0].button("Test connection", key="conn_test"):
        result = _api_post(f"/connections/{conn_id}/test", {})
        if result is not None:
            (st.success if result["status"] == "ok" else st.error)(result["message"])
    if action_cols[1].button("Delete connection", key="conn_delete"):
        try:
            requests.delete(
                f"{API_BASE}/connections/{conn_id}",
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            st.rerun()
        except requests.RequestException as exc:
            st.error(str(exc))

    st.markdown("#### Register a table as a dataset")
    if st.button("Discover tables", key="conn_discover"):
        st.session_state["conn_tables"] = _api_get(f"/connections/{conn_id}/tables")
        st.session_state["conn_tables_for"] = conn_id

    listing = (
        st.session_state.get("conn_tables")
        if st.session_state.get("conn_tables_for") == conn_id
        else None
    )
    if listing and listing["tables"]:
        table_labels = {
            (f"{t['schema_name']}.{t['name']}" if t["schema_name"] else t["name"]): t
            for t in listing["tables"]
        }
        chosen = st.selectbox("Table", list(table_labels.keys()), key="conn_table")
        table = table_labels[chosen]
        ds_name = st.text_input("Dataset name (optional)", value=table["name"], key="conn_ds_name")
        if st.button("Register table", type="primary", key="conn_reg"):
            body = {
                "schema_name": table["schema_name"],
                "table": table["name"],
                "name": ds_name or None,
            }
            meta = _api_post(f"/connections/{conn_id}/datasets", body, ok=201)
            if meta is not None:
                st.success(
                    f"Registered '{meta['filename']}' "
                    f"({meta['rows']} rows × {meta['columns']} cols"
                    + (", truncated" if meta.get("truncated") else "")
                    + "). It's now available in Datasets, Ask Data and Reports."
                )
    else:
        st.info("No tables discovered in this connection.")


def render_forecast_tab() -> None:
    """Render the forecasting / anomaly-detection interface."""
    st.subheader("Forecast & detect anomalies")

    datasets = fetch_datasets()
    if not datasets:
        st.info("Upload or connect a dataset first.")
        return

    options = {
        f"{item['filename']}  ·  {item['rows']}×{item['columns']}": item["id"]
        for item in datasets
    }
    selected_label = st.selectbox("Dataset", list(options.keys()), key="fc_ds")
    question = st.text_input(
        "Your question",
        placeholder="e.g. Forecast revenue for the next 6 months / "
        "Find anomalies in daily sales",
        key="fc_q",
    )

    if st.button("Run", type="primary", key="fc_run"):
        if not question.strip():
            st.warning("Please enter a question.")
            return
        with st.spinner("Modeling…"):
            result = _api_post(
                "/forecast",
                {"dataset_id": options[selected_label], "question": question.strip()},
            )
        if result is None:
            return

        st.markdown("#### Answer")
        st.text(result["answer"])

        cols = st.columns(4)
        cols[0].metric("Method", result["method_used"])
        cols[1].metric("Fallback", "yes" if result["fallback_used"] else "no")
        cols[2].metric("Data points", result["data_points"])
        cols[3].metric("Horizon", result["horizon"])

        if result.get("chart_spec"):
            st.plotly_chart(go.Figure(result["chart_spec"]), use_container_width=True)
        if result.get("table_data"):
            with st.expander("Data"):
                st.dataframe(
                    result["table_data"], use_container_width=True, hide_index=True
                )


def render_reports_tab() -> None:
    """Render the report-generation interface."""
    st.subheader("Generate a PDF report")

    datasets = fetch_datasets()
    if not datasets:
        st.info("Upload a dataset first, then generate a report.")
        return

    options = {
        f"{item['filename']}  ·  {item['rows']}×{item['columns']}": item["id"]
        for item in datasets
    }
    selected_label = st.selectbox("Dataset", list(options.keys()), key="reports_ds")
    questions_text = st.text_area(
        "Optional questions (one per line) — these add AI-generated sections",
        placeholder="Top 5 products by revenue\nRevenue by region",
        key="reports_questions",
    )

    if st.button("Generate Report", type="primary", key="reports_gen"):
        questions = [q.strip() for q in questions_text.splitlines() if q.strip()]
        with st.spinner("Building report…"):
            metadata = post_report(options[selected_label], questions)
        if metadata is None:
            return

        st.success("Report generated.")
        info_cols = st.columns(3)
        info_cols[0].metric(
            "Deterministic sections", metadata["deterministic_section_count"]
        )
        info_cols[1].metric("AI sections", metadata["ai_section_count"])
        info_cols[2].metric("Size", f"{metadata['size_bytes'] / 1024:.1f} KB")
        st.caption(
            f"Report ID: {metadata['report_id']} · "
            f"version {metadata['report_version']} · "
            f"generated {metadata['generated_at']}"
        )

        pdf_bytes = fetch_report_pdf(metadata["report_id"])
        if pdf_bytes is not None:
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name=f"report_{metadata['report_id']}.pdf",
                mime="application/pdf",
                key="reports_dl",
            )


def render_upload_tab() -> None:
    """Render the file-upload interface."""
    st.subheader("Upload a dataset")
    uploaded = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=False,
        key="upload_file",
    )

    if uploaded is None:
        st.info("Select a file to begin.")
        return

    if st.button("Upload", type="primary", key="upload_btn"):
        with st.spinner("Uploading and parsing…"):
            result = upload_dataset(
                uploaded.name,
                uploaded.getvalue(),
                uploaded.type or "application/octet-stream",
            )
        if result is not None:
            dataset = result["dataset"]
            st.success(result["message"])
            st.json(dataset)


def render_datasets_tab() -> None:
    """Render the list of stored datasets."""
    st.subheader("Stored datasets")
    if st.button("Refresh", key="ds_refresh"):
        st.rerun()

    datasets = fetch_datasets()
    if not datasets:
        st.info("No datasets uploaded yet.")
        return

    st.caption(f"{len(datasets)} dataset(s) found.")
    st.dataframe(
        [
            {
                "Filename": item["filename"],
                "Type": item["file_type"],
                "Rows": item["rows"],
                "Columns": item["columns"],
                "Size (bytes)": item["size_bytes"],
                "Uploaded (UTC)": item["created_at"],
            }
            for item in datasets
        ],
        use_container_width=True,
    )

    st.divider()
    st.markdown("### Preview a dataset")

    # Map a human-readable label to each dataset id for the selector.
    options = {
        f"{item['filename']}  ·  {item['rows']}×{item['columns']}": item["id"]
        for item in datasets
    }
    selected_label = st.selectbox("Select a dataset", list(options.keys()), key="ds_select")

    if st.button("Preview", type="primary", key="ds_preview"):
        with st.spinner("Loading preview…"):
            preview = fetch_preview(options[selected_label])
        if preview is not None:
            render_preview(preview)


def main() -> None:
    """Compose the Streamlit page."""
    st.set_page_config(page_title="Universal Data Assistant", layout="wide")
    st.title("📊 Universal Data Assistant")
    st.caption(f"Connected to backend: {BACKEND_URL}")

    upload_tab, connect_tab, datasets_tab, ask_tab, forecast_tab, reports_tab = (
        st.tabs(
            ["Upload", "Connect DB", "Datasets", "Ask Data", "Forecast", "Reports"]
        )
    )
    with upload_tab:
        render_upload_tab()
    with connect_tab:
        render_connect_tab()
    with datasets_tab:
        render_datasets_tab()
    with ask_tab:
        render_ask_tab()
    with forecast_tab:
        render_forecast_tab()
    with reports_tab:
        render_reports_tab()


if __name__ == "__main__":
    main()

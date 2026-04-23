import os

import streamlit as st

try:
    for _key, _val in st.secrets.items():
        if isinstance(_val, (str, int, float, bool)) and _key not in os.environ:
            os.environ[_key] = str(_val)
except (FileNotFoundError, Exception):
    pass

from auth import authenticate_user, clear_auth_session, get_authenticated_user, init_auth_db, register_user
from billing import (
    create_checkout_session_url_for_user,
    get_user_status,
    init_billing_db,
    record_free_download_use,
    record_free_file_use,
    verify_checkout_session,
)
from data_processor import clean_uploaded_csv
from db import check_database_connection
from observability import configure_logging, get_logger, init_sentry, required_env_vars
from visualizer import generate_report_charts


st.set_page_config(page_title="CSV Cleaning SaaS", layout="wide")
configure_logging("streamlit-app")
init_sentry("streamlit-app")
logger = get_logger("app")

init_billing_db()
init_auth_db()

FREE_FILE_LIMIT = 1
FREE_DOWNLOAD_LIMIT = 1
MISSING_ENV = required_env_vars(
    [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_PRICE_ID",
        "STRIPE_SUCCESS_URL",
        "STRIPE_CANCEL_URL",
    ]
)

st.title("CSV Cleaning & Reporting")
st.caption("Upload raw CSV files, clean them, and generate visual reports.")
if MISSING_ENV:
    st.error(f"Missing required environment variables: {', '.join(MISSING_ENV)}")
    st.stop()
if not check_database_connection():
    st.error("Database connection failed. Check DATABASE_URL and try again.")
    st.stop()

st.sidebar.header("Navigation")
section = st.sidebar.radio(
    "Go to",
    ("Data Cleaning", "Report Generation"),
)

st.sidebar.markdown("---")
if "checkout_url" not in st.session_state:
    st.session_state["checkout_url"] = None

authenticated_user = get_authenticated_user(st.session_state)
if authenticated_user:
    user_email = authenticated_user["email"]
    user_id = authenticated_user["id"]
    st.sidebar.success(f"Signed in as: {user_email}")
    if st.sidebar.button("Sign out"):
        clear_auth_session(st.session_state)
        logger.info("user_signed_out", extra={"user_id": user_id})
        st.rerun()
else:
    auth_mode = st.sidebar.radio("Account", ("Sign in", "Create account"))
    if auth_mode == "Sign in":
        with st.sidebar.form("login_form", clear_on_submit=False):
            login_email = st.text_input("Email", key="login_email").strip().lower()
            login_password = st.text_input("Password", type="password", key="login_password")
            login_submit = st.form_submit_button("Sign in")
        if login_submit:
            ok, message = authenticate_user(login_email, login_password, st.session_state)
            if ok:
                logger.info("user_signed_in", extra={"email": login_email})
                st.rerun()
            st.sidebar.error(message)
    else:
        with st.sidebar.form("register_form", clear_on_submit=True):
            reg_email = st.text_input("Email", key="reg_email").strip().lower()
            reg_password = st.text_input("Password (min 8 chars)", type="password", key="reg_password")
            reg_submit = st.form_submit_button("Create account")
        if reg_submit:
            ok, message = register_user(reg_email, reg_password)
            if ok:
                st.sidebar.success(message)
            else:
                st.sidebar.error(message)
    authenticated_user = get_authenticated_user(st.session_state)
    user_email = authenticated_user["email"] if authenticated_user else None
    user_id = authenticated_user["id"] if authenticated_user else None

if authenticated_user:
    status = get_user_status(user_id, user_email)
else:
    status = {
        "has_paid": False,
        "free_files_used": 0,
        "free_downloads_used": 0,
        "subscription_status": None,
    }

paid_badge = "Pro" if status["has_paid"] else "Free"
st.sidebar.caption(f"Current plan: {paid_badge}")
if authenticated_user and st.sidebar.button("Refresh plan status"):
    st.rerun()

uploaded_file = st.sidebar.file_uploader(
    "Upload a CSV file",
    type=["csv"],
    help="Only CSV files are supported in this initial scaffold.",
)

session_id = st.query_params.get("session_id")
if session_id and authenticated_user and not status["has_paid"]:
    try:
        was_verified = verify_checkout_session(session_id, user_id)
        if was_verified:
            st.success("Payment confirmed. Pro features are now unlocked.")
            status = get_user_status(user_id, user_email)
    except Exception as error:
        st.warning(f"Could not verify payment session yet: {error}")

if uploaded_file is not None and authenticated_user:
    st.success(f"File uploaded: {uploaded_file.name}")
elif uploaded_file is not None and not authenticated_user:
    st.warning("Sign in to start processing files.")
else:
    st.warning("Please upload a CSV file to continue.")

if section == "Data Cleaning":
    st.header("Data Cleaning")
    st.write("Upload a CSV to clean it. Free users can clean one file and download once.")

    def _show_upgrade_callout() -> None:
        st.info("Upgrade to Pro to unlock visualization reports and unlimited downloads.")
        st.caption("In production, Stripe webhooks unlock your plan automatically after payment.")
        if st.button("Create Stripe Checkout Session"):
            try:
                checkout_url = create_checkout_session_url_for_user(user_id, user_email)
                st.session_state["checkout_url"] = checkout_url
            except Exception as error:
                st.error(f"Unable to create checkout session: {error}")
        if st.session_state.get("checkout_url"):
            st.link_button("Pay with Stripe Checkout", st.session_state["checkout_url"])

    if not authenticated_user:
        st.info("Sign in or create an account from the sidebar to continue.")
    elif uploaded_file is not None:
        try:
            if not status["has_paid"] and status["free_files_used"] >= FREE_FILE_LIMIT:
                st.warning("Free limit reached: one cleaned file.")
                _show_upgrade_callout()
                st.stop()

            cleaned_df = clean_uploaded_csv(uploaded_file)
            st.subheader("Cleaned Data")
            st.dataframe(cleaned_df, use_container_width=True)

            cleaned_csv = cleaned_df.to_csv(index=False).encode("utf-8")
            download_disabled = (
                not status["has_paid"] and status["free_downloads_used"] >= FREE_DOWNLOAD_LIMIT
            )
            st.download_button(
                label="Download Cleaned CSV",
                data=cleaned_csv,
                file_name="cleaned_data.csv",
                mime="text/csv",
                disabled=download_disabled,
                on_click=(record_free_download_use if not status["has_paid"] else None),
                args=((user_id, user_email) if not status["has_paid"] else ()),
            )
            if download_disabled:
                st.warning("Free download limit reached.")
                _show_upgrade_callout()

            file_key = f"{uploaded_file.name}:{uploaded_file.size}"
            last_recorded_key = st.session_state.get("last_free_file_key")
            if not status["has_paid"] and file_key != last_recorded_key:
                record_free_file_use(user_id, user_email)
                st.session_state["last_free_file_key"] = file_key
                status = get_user_status(user_id, user_email)

            if not status["has_paid"]:
                st.info("Visualization dashboard is a Pro feature.")
                _show_upgrade_callout()
            elif st.button("Generate Report"):
                charts, messages = generate_report_charts(cleaned_df)
                st.subheader("Visualization Dashboard")
                for message in messages:
                    st.info(message)
                if not charts:
                    st.warning("No charts were generated for this dataset.")
                else:
                    for chart_title, figure in charts:
                        st.markdown(f"**{chart_title}**")
                        st.pyplot(figure, clear_figure=True)
        except Exception as error:
            st.error(f"Unable to process file: {error}")
    else:
        st.info("Upload a CSV file from the sidebar to begin cleaning.")

    with st.container(border=True):
        st.subheader("Upcoming Steps")
        st.markdown(
            """
            - Validate schema and required columns
            - Handle null values and duplicates
            - Normalize formats (dates, numerics, categories)
            """
        )

elif section == "Report Generation":
    st.header("Report Generation")
    st.write("Pro users can generate full visualization reports in the Data Cleaning view.")
    if not authenticated_user:
        st.info("Sign in to see your plan status.")
    elif not status["has_paid"]:
        st.warning("Upgrade required for report generation.")
    else:
        st.success("Pro unlocked. Upload and clean data, then click Generate Report.")

    with st.container(border=True):
        st.subheader("Upcoming Steps")
        st.markdown(
            """
            - Select chart types and metrics
            - Build summary plots with Matplotlib
            - Export insights and downloadable artifacts
            """
        )

st.markdown("---")
privacy_url = os.getenv("PRIVACY_URL", "https://example.com/privacy")
terms_url = os.getenv("TERMS_URL", "https://example.com/terms")
retention_url = os.getenv("RETENTION_URL", "https://example.com/operations")
st.markdown(
    f"[Privacy Policy]({privacy_url}) | [Terms of Service]({terms_url}) | [Data Retention]({retention_url})"
)

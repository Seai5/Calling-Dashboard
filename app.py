import pandas as pd
import streamlit as st
import altair as alt

# ------------------- Page Config -------------------
st.set_page_config(page_title="Call Analytics Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("Call Data Analytics Dashboard (Unique Phone Numbers)")

# ------------------- Session State -------------------
for key in ["df_merged", "df_unique", "summary", "agent_summary", "list_disposition_summary", "selected_metrics"]:
    if key not in st.session_state:
        st.session_state[key] = None

if st.session_state.selected_metrics is None:
    st.session_state.selected_metrics = set()

# ------------------- Sidebar -------------------
with st.sidebar:
    st.header("Upload & Filters")
    uploaded_calling = st.file_uploader("Upload Calling.csv", type=["csv"], key="calling")

    if st.button("Clear All Data & Reset", type="primary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.session_state.selected_metrics = set()
        st.success("All data cleared!")
        st.rerun()

# ------------------- Core Functions -------------------
def process_data(df_calling):
    df2 = pd.read_csv("Disposition_.csv")
    df = df_calling.copy()

    # Clean Disposition
    df["Sub Sub Disposition"] = (
        df["Sub Sub Disposition"]
        .replace("", pd.NA)
        .fillna(df["Disposition"])
        .fillna(df["Dialer Status"])
    )

    # Talk Sec to seconds
    df["Talk Sec"] = pd.to_timedelta(df["Talk Sec"], errors='coerce').dt.total_seconds().fillna(0).astype(float)

    # Date & Hour
    df["Call Start Time"] = pd.to_datetime(df["Call Start Time"], errors='coerce')
    df["Call Date"] = df["Call Start Time"].dt.date
    df["Hour"] = df["Call Start Time"].dt.hour

    # Talk Slot Category
    def slot_category(sec):
        if sec == 0: return "No Interaction"
        elif sec < 30: return "Below 30s"
        elif sec < 60: return "30s–1min"
        elif sec < 120: return "1–2min"
        else: return "Above 2 Min"
    df["Slot"] = df["Talk Sec"].apply(slot_category)

    # Merge with Disposition Mapping
    df_merged = pd.merge(df, df2, left_on="Sub Sub Disposition", right_on="Call Disposed Status", how="left")

    # CRITICAL: Deduplicate by Phone Number → Keep BEST call (longest talk time)
    df_merged = df_merged.sort_values("Talk Sec", ascending=False)
    df_unique = df_merged.drop_duplicates(subset="Phone Number", keep="first").copy()

    return df_merged, df_unique


def generate_metrics(df_unique):
    total_dialled = len(df_unique)
    connected = df_unique[df_unique["Connected/Not Connected"] == "Connected"]
    unique_connected = len(connected)

    gt_30s  = len(connected[connected["Slot"].isin(["30s–1min", "1–2min", "Above 2 Min"])])
    gt_1min = len(connected[connected["Slot"].isin(["1–2min", "Above 2 Min"])])
    gt_2min = len(connected[connected["Slot"] == "Above 2 Min"])

    connect_pct = round(unique_connected / total_dialled * 100, 2) if total_dialled else 0

    def pct(val): return round(val / unique_connected * 100, 2) if unique_connected else 0

    positive_dispositions = ["Follow Up", "Virtual Meet Proposed", "Virtual Meet Confirmed"]
    disp_counts = df_unique["Primary Disposition"].value_counts()

    sdw = disp_counts.get("SDW", 0)
    lost = disp_counts.get("Lost", 0)
    fw = disp_counts.get("Follow Up", 0)
    vp = disp_counts.get("Virtual Meet Proposed", 0)
    vc = disp_counts.get("Virtual Meet Confirmed", 0)
    positive_total = fw + vp + vc

    summary = pd.DataFrame({
        "Metric": [
            "Unique Data Dialled", "Unique Connected", "Unique Connected >30s",
            "Unique Connected >1min", "Unique Connected >2min", "Connect %",
            "SDW (%)", "Lost (%)", "Follow Up (%)", "Virtual Meet Proposed (%)", "Virtual Meet Confirmed (%)", "Total Positive (%)"
        ],
        "Value": [
            f"{total_dialled:,}", f"{unique_connected:,}", f"{gt_30s:,}",
            f"{gt_1min:,}", f"{gt_2min:,}", f"{connect_pct}%",
            f"{pct(sdw)}%", f"{pct(lost)}%", f"{pct(fw)}%", f"{pct(vp)}%", f"{pct(vc)}%", f"{pct(positive_total)}%"
        ]
    })

    # Agent Summary - Fully Unique
    agent_base = df_unique.groupby("Agent Name").agg(
        Unique_Contacts=("Phone Number", "count"),
        Unique_Connected_GT30s=("Slot", lambda x: x.isin(["30s–1min", "1–2min", "Above 2 Min"]).sum()),
        Unique_Connected_GT1min=("Slot", lambda x: x.isin(["1–2min", "Above 2 Min"]).sum()),
        Unique_Connected_GT2min=("Slot", lambda x: (x == "Above 2 Min").sum())
    ).reset_index()

    # Positive Outcomes per Agent
    agent_positive = df_unique[df_unique["Primary Disposition"].isin(positive_dispositions)]
    positive_count = agent_positive.groupby("Agent Name").size().reset_index(name="Positive_Outcomes")

    agent_summary = pd.merge(agent_base, positive_count, on="Agent Name", how="left").fillna(0)
    agent_summary["Positive_Outcomes"] = agent_summary["Positive_Outcomes"].astype(int)
    agent_summary["Effort_to_Positive"] = (agent_summary["Unique_Contacts"] / agent_summary["Positive_Outcomes"]).round(2)
    agent_summary["Effort_to_Positive"] = agent_summary["Effort_to_Positive"].replace([float('inf'), 0], "-")

    # Disposition breakdown per agent
    disp_pivot = df_unique.groupby(["Agent Name", "Primary Disposition"]).size().unstack(fill_value=0).reset_index()
    agent_summary = pd.merge(agent_summary, disp_pivot, on="Agent Name", how="left").fillna(0)

    # Reorder columns
    cols_order = ["Agent Name", "Unique_Contacts", "Unique_Connected_GT30s", "Unique_Connected_GT1min",
                  "Unique_Connected_GT2min", "Positive_Outcomes", "Effort_to_Positive"] + \
                 sorted([c for c in agent_summary.columns if c not in ["Agent Name", "Unique_Contacts", "Unique_Connected_GT30s",
                  "Unique_Connected_GT1min", "Unique_Connected_GT2min", "Positive_Outcomes", "Effort_to_Positive"]])
    agent_summary = agent_summary[cols_order]

    # List Name vs Disposition Summary
    if "List Name" in df_unique.columns and df_unique["List Name"].notna().any():
        list_disp = df_unique.groupby(["List Name", "Primary Disposition"]).size().unstack(fill_value=0)
        list_disp["Total_Unique"] = list_disp.sum(axis=1)
        list_disp["Positive"] = list_disp[[col for col in positive_dispositions if col in list_disp.columns]].sum(axis=1)
        list_disp["Positive_%"] = (list_disp["Positive"] / list_disp["Total_Unique"] * 100).round(2)
        cols = ["Total_Unique", "Positive", "Positive_%"] + sorted([c for c in list_disp.columns if c not in ["Total_Unique", "Positive", "Positive_%"]])
        list_disp_summary = list_disp[cols].sort_values("Total_Unique", ascending=False)
    else:
        list_disp_summary = pd.DataFrame()

    return summary, agent_summary, list_disp_summary


# ------------------- Main Processing -------------------
if uploaded_calling:
    try:
        df_calling = pd.read_csv(uploaded_calling)
        df_merged, df_unique = process_data(df_calling)

        # Filters
        with st.sidebar:
            st.subheader("Filters")

            min_date = pd.to_datetime(df_unique["Call Date"]).min().date()
            max_date = pd.to_datetime(df_unique["Call Date"]).max().date()
            date_range = st.date_input("Date Range", [min_date, max_date], min_value=min_date, max_value=max_date)

            if len(date_range) == 2:
                start_date, end_date = date_range
                df_unique = df_unique[(pd.to_datetime(df_unique["Call Date"]) >= pd.to_datetime(start_date)) &
                                      (pd.to_datetime(df_unique["Call Date"]) <= pd.to_datetime(end_date))]

            if "List Name" in df_unique.columns and df_unique["List Name"].notna().any():
                lists = ["All"] + sorted(df_unique["List Name"].dropna().unique().tolist())
                chosen_list = st.selectbox("List Name", lists, index=0)
                if chosen_list != "All":
                    df_unique = df_unique[df_unique["List Name"] == chosen_list]

            if st.button("Apply Filters & Refresh", type="secondary"):
                st.rerun()

        # Generate Metrics
        summary, agent_summary, list_disp_summary = generate_metrics(df_unique)

        # Save to session
        st.session_state.df_unique = df_unique
        st.session_state.summary = summary
        st.session_state.agent_summary = agent_summary
        st.session_state.list_disposition_summary = list_disp_summary

        st.success(f"Unique Phone Analysis Ready | Total Unique Numbers: {len(df_unique):,}")

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Please upload **Calling.csv** to begin.")
    st.stop()

# ================================= DASHBOARD =================================
df_unique = st.session_state.df_unique
summary = st.session_state.summary
agent_summary = st.session_state.agent_summary
list_disp_summary = st.session_state.list_disposition_summary

# Summary Metrics
st.subheader("Overall Summary (Unique Phone Numbers Only)")
summary_display = summary.copy()
summary_display["Select"] = summary_display["Metric"].isin(st.session_state.selected_metrics)

edited = st.data_editor(
    summary_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Select": st.column_config.CheckboxColumn("Highlight", default=False),
        "Metric": st.column_config.TextColumn("Metric", disabled=True),
        "Value": st.column_config.TextColumn("Value", disabled=True),
    },
    disabled=["Metric", "Value"]
)

new_sel = set(edited[edited["Select"]]["Metric"])
if new_sel != st.session_state.selected_metrics:
    st.session_state.selected_metrics = new_sel
    st.rerun()

# Call Volume by Hour (Unique Phones)
st.subheader("Unique Phone Numbers Dialled by Hour")
hourly = df_unique.groupby("Hour").size().reset_index(name="Unique_Phones")
chart = alt.Chart(hourly).mark_bar(color="#0068c9").encode(
    x=alt.X("Hour:O", title="Hour of Day"),
    y=alt.Y("Unique_Phones:Q", title="Unique Phone Numbers"),
    tooltip=["Hour", "Unique_Phones"]
).properties(height=350, title="Unique Customers Reached by Hour")
st.altair_chart(chart, use_container_width=True)

# Top 10 Agents by Positive Outcomes
st.subheader("Top 10 Agents by Positive Outcomes (Unique Customers)")
top10 = agent_summary.sort_values("Positive_Outcomes", ascending=False).head(10)
st.dataframe(top10[["Agent Name", "Unique_Contacts", "Positive_Outcomes", "Effort_to_Positive"]], use_container_width=True)

bar = alt.Chart(top10).mark_bar(color="#2ecc71").encode(
    y=alt.Y("Agent Name:N", sort="-x", title="Agent"),
    x=alt.X("Positive_Outcomes:Q", title="Positive Outcomes"),
    tooltip=["Agent Name", "Positive_Outcomes", "Unique_Contacts", "Effort_to_Positive"]
).properties(height=400, title="Top Performers - Unique Positive Outcomes")
st.altair_chart(bar, use_container_width=True)

# List-wise Report
st.subheader("List Name vs Primary Disposition (Unique Phone Numbers)")
if not list_disp_summary.empty:
    styled = list_disp_summary.style.format("{:,}").background_gradient(cmap="Blues", subset=["Total_Unique", "Positive"])
    st.dataframe(styled, use_container_width=True)
    st.download_button(
        "Download List-wise Unique Report",
        data=list_disp_summary.to_csv().encode(),
        file_name="List_Name_vs_Disposition_Unique.csv",
        mime="text/csv"
    )
else:
    st.info("No List Name data available.")

# Drill-Down
if st.session_state.selected_metrics:
    st.markdown("### Drill-Down: Selected Metrics")
    for metric in st.session_state.selected_metrics:
        st.markdown(f"#### {metric}")
        if "Unique Data Dialled" in metric:
            filt = df_unique.copy()
        elif "Unique Connected" in metric and ">" not in metric:
            filt = df_unique[df_unique["Connected/Not Connected"] == "Connected"]
        elif ">30s" in metric:
            filt = df_unique[df_unique["Slot"].isin(["30s–1min", "1–2min", "Above 2 Min"])]
        elif ">1min" in metric:
            filt = df_unique[df_unique["Slot"].isin(["1–2min", "Above 2 Min"])]
        elif ">2min" in metric:
            filt = df_unique[df_unique["Slot"] == "Above 2 Min"]
        elif "(%)" in metric:
            disp = metric.split(" (%)")[0].split(" (")[0]
            filt = df_unique[df_unique["Primary Disposition"] == disp]
        else:
            filt = pd.DataFrame()

        if not filt.empty:
            st.metric("Unique Records", len(filt))
            st.dataframe(filt, use_container_width=True)
            st.download_button(f"Download {metric}", filt.to_csv(index=False).encode(),
                               file_name=f"{metric.replace(' ', '_')}.csv", mime="text/csv", key=metric)
        else:
            st.info("No matching data.")

# Full Agent Performance
st.subheader("Agent Performance Summary (Unique Phone Numbers)")
st.dataframe(agent_summary, use_container_width=True)
st.download_button("Download Full Agent Report", agent_summary.to_csv(index=False).encode(),
                   file_name="Agent_Performance_Unique_Phone.csv", mime="text/csv")

# Raw Unique Data
with st.expander("View Raw Unique Data (One Row Per Phone Number)"):
    st.dataframe(df_unique, use_container_width=True)

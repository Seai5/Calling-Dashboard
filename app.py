import pandas as pd
import streamlit as st
import altair as alt

# ------------------- Page Config -------------------
st.set_page_config(page_title="Call Analytics Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("Call Data Analytics Dashboard")

# ------------------- Session State -------------------
for key in ["df_merged", "summary", "agent_summary", "list_disposition_summary", "selected_metrics"]:
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
    df["Talk Sec"] = pd.to_timedelta(df["Talk Sec"], errors='coerce').dt.total_seconds().fillna(0)

    # Date & Hour
    df["Call Start Time"] = pd.to_datetime(df["Call Start Time"], errors='coerce')
    df["Call Date"] = df["Call Start Time"].dt.date
    df["Hour"] = df["Call Start Time"].dt.hour

    # Talk Slot Category
    def slot_category(sec):
        if sec == 0: return "No Interaction"
        elif sec < 30: return "Below 30s"
        elif sec < 60: return "Above 30s"
        elif sec < 120: return "Above 1 Min"
        else: return "Above 2 Min"
    df["Slot"] = df["Talk Sec"].apply(slot_category)

    # Merge with Disposition Mapping
    df_merged = pd.merge(df, df2, left_on="Sub Sub Disposition", right_on="Call Disposed Status", how="left")
    return df_merged


def generate_metrics(df_merged):
    # Overall Summary
    unique_dialled   = df_merged["Phone Number"].nunique()
    unique_connected = df_merged[df_merged["Connected/Not Connected"] == "Connected"]["Phone Number"].nunique()
    gt_30s  = df_merged[df_merged["Slot"] == "Above 30s"]["Phone Number"].nunique()
    gt_1min = df_merged[df_merged["Slot"] == "Above 1 Min"]["Phone Number"].nunique()
    gt_2min = df_merged[df_merged["Slot"] == "Above 2 Min"]["Phone Number"].nunique()
    connect_pct = round(unique_connected / unique_dialled * 100, 2) if unique_dialled else 0

    def pct(val): return round(val / unique_connected * 100, 2) if unique_connected else 0

    sdw = (df_merged["Primary Disposition"] == "SDW").sum()
    lost = (df_merged["Primary Disposition"] == "Lost").sum()
    fw   = (df_merged["Primary Disposition"] == "Follow Up").sum()
    vp   = (df_merged["Primary Disposition"] == "Virtual Meet Proposed").sum()
    vc   = (df_merged["Primary Disposition"] == "Virtual Meet Confirmed").sum()

    summary = pd.DataFrame({
        "Metric": [
            "Unique Data Dialled", "Unique Connected Call", "Unique Connected Call > 30s",
            "Unique Connected Call > 1min", "Unique Connected Call > 2min", "Connect %",
            "SDW (%)", "Lost (%)", "Follow Up (%)", "Virtual Meet Proposed (%)", "Virtual Meet Confirmed (%)"
        ],
        "Value": [
            unique_dialled, unique_connected, gt_30s, gt_1min, gt_2min,
            f"{connect_pct}%", f"{pct(sdw)}%", f"{pct(lost)}%", f"{pct(fw)}%", f"{pct(vp)}%", f"{pct(vc)}%"
        ]
    })

    # Agent Summary (Cleaned - No Hold/Mute/Transfer)
    agent_base = df_merged.groupby("Agent Name").agg(
        Total_Calls=("Phone Number", "nunique"),
        Connected_GT_30s=("Slot", lambda x: (x == "Above 30s").sum()),
        Connected_GT_1min=("Slot", lambda x: (x == "Above 1 Min").sum()),
        Connected_GT_2min=("Slot", lambda x: (x == "Above 2 Min").sum())
    ).reset_index()

    disposition_pivot = df_merged.groupby(["Agent Name", "Primary Disposition"]).size().unstack(fill_value=0).reset_index()
    agent_summary = pd.merge(agent_base, disposition_pivot, on="Agent Name", how="left", suffixes=('', '_disp')).fillna(0)

    # Positive & Ratio
    pos_cols = ["Follow Up", "Virtual Meet Proposed", "Virtual Meet Confirmed"]
    existing_pos = [c for c in pos_cols if c in agent_summary.columns]
    agent_summary["Positive"] = agent_summary[existing_pos].sum(axis=1)
    agent_summary["Effort_to_Positive"] = agent_summary.apply(
        lambda r: round(r["Total_Calls"] / r["Positive"], 2) if r["Positive"] > 0 else None, axis=1)

    # Reorder
    base_cols = ["Agent Name", "Total_Calls", "Connected_GT_30s", "Connected_GT_1min", "Connected_GT_2min",
                 "Positive", "Effort_to_Positive"]
    other_cols = sorted([c for c in agent_summary.columns if c not in base_cols])
    agent_summary = agent_summary[base_cols + other_cols]

    # === LIST NAME vs PRIMARY DISPOSITION + POSITIVE COLUMN ===
    if "List Name" in df_merged.columns and "Primary Disposition" in df_merged.columns:
        # Pivot: List Name × Primary Disposition
        list_disp_summary = df_merged.groupby(["List Name", "Primary Disposition"]).size().unstack(fill_value=0)

        # Total Calls per List
        list_disp_summary["Total Calls"] = list_disp_summary.sum(axis=1)

        # Define Positive Dispositions
        positive_dispositions = [
            "Follow Up",
            "Virtual Meet Proposed", 
            "Virtual Meet Confirmed"
        ]

        # Add "Positive" column = sum of the positive dispositions (only if they exist)
        list_disp_summary["Positive"] = list_disp_summary[
            [col for col in positive_dispositions if col in list_disp_summary.columns]
        ].sum(axis=1)

        # Optional: Add Positive % 
        list_disp_summary["Positive %"] = (
            list_disp_summary["Positive"] / list_disp_summary["Total Calls"] * 100
        ).round(2).fillna(0)

        # Reorder columns: Total Calls and Positive first, then dispositions
        cols = ["Total Calls", "Positive", "Positive %"] + \
            [col for col in sorted(list_disp_summary.columns) if col not in ["Total Calls", "Positive", "Positive %"]]
        list_disp_summary = list_disp_summary[cols]

        # Sort by Total Calls
        list_disp_summary = list_disp_summary.sort_values("Total Calls", ascending=False)

        # # Grand Total row
        # list_disp_summary.loc["Grand Total"] = list_disp_summary.sum(numeric_only=True)
        # list_disp_summary.loc["Grand Total", ["Positive %"]] = (
        #     list_disp_summary.loc["Grand Total", "Positive"] / 
        #     list_disp_summary.loc["Grand Total", "Total Calls"] * 100
        # ).round(2)

    else:
        list_disp_summary = pd.DataFrame()

    return summary, agent_summary, list_disp_summary


# ------------------- Main Processing -------------------
if uploaded_calling:
    try:
        df_calling = pd.read_csv(uploaded_calling)
        df_merged = process_data(df_calling)

        # Filters
        with st.sidebar:
            st.subheader("Filters")

            min_date = df_merged["Call Date"].min()
            max_date = df_merged["Call Date"].max()
            date_range = st.date_input("Date Range", [min_date, max_date], min_value=min_date, max_value=max_date)

            if len(date_range) == 2:
                start_date, end_date = date_range
                df_merged = df_merged[(df_merged["Call Date"] >= start_date) & (df_merged["Call Date"] <= end_date)]

            if "List Name" in df_merged.columns and df_merged["List Name"].notna().any():
                lists = ["All"] + sorted(df_merged["List Name"].dropna().unique().tolist())
                chosen_list = st.selectbox("List Name", lists, index=0)
                if chosen_list != "All":
                    df_merged = df_merged[df_merged["List Name"] == chosen_list]

            if st.button("Apply Filters & Refresh", type="secondary"):
                st.rerun()

        # Generate All Metrics
        summary, agent_summary, list_disp_summary = generate_metrics(df_merged)

        # Save to session
        st.session_state.df_merged = df_merged
        st.session_state.summary = summary
        st.session_state.agent_summary = agent_summary
        st.session_state.list_disposition_summary = list_disp_summary

        st.success(f"Data loaded successfully | Total Records: {len(df_merged):,}")

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Please upload **Calling.csv** to begin.")
    st.stop()

# ================================= DASHBOARD =================================
df_merged = st.session_state.df_merged
summary = st.session_state.summary
agent_summary = st.session_state.agent_summary
list_disp_summary = st.session_state.list_disposition_summary

# Summary Metrics Table
st.subheader("Overall Summary Metrics")
if summary is not None:
    summary_display = summary.copy()
    summary_display["Select"] = summary_display["Metric"].isin(st.session_state.selected_metrics)

    edited = st.data_editor(
        summary_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", default=False),
            "Metric": st.column_config.TextColumn("Metric", disabled=True),
            "Value": st.column_config.TextColumn("Value", disabled=True),
        },
        disabled=["Metric", "Value"]
    )

    new_sel = set(edited[edited["Select"]]["Metric"])
    if new_sel != st.session_state.selected_metrics:
        st.session_state.selected_metrics = new_sel
        st.rerun()

# Call Volume by Hour
st.subheader("Call Volume by Hour of Day")
hourly = df_merged.groupby("Hour").size().reset_index(name="Call Count")
chart = alt.Chart(hourly).mark_bar(color="#0068c9").encode(
    x=alt.X("Hour:O", title="Hour"),
    y=alt.Y("Call Count:Q"),
    tooltip=["Hour", "Call Count"]
).properties(height=350)
st.altair_chart(chart, use_container_width=True)

# Top 10 Agents
st.subheader("Top 10 Agents by Positive Outcomes")
top10 = agent_summary.sort_values("Positive", ascending=False).head(10)
st.dataframe(top10[["Agent Name", "Total_Calls", "Positive", "Effort_to_Positive"]], use_container_width=True)

bar = alt.Chart(top10).mark_bar(color="#2ecc71").encode(
    y=alt.Y("Agent Name:N", sort="-x"),
    x="Positive:Q",
    tooltip=["Agent Name", "Positive", "Total_Calls", "Effort_to_Positive"]
).properties(height=400)
st.altair_chart(bar, use_container_width=True)

# NEW: List Name vs Primary Disposition Summary
st.subheader("List Name vs Primary Disposition Summary")
if not list_disp_summary.empty:
    st.dataframe(list_disp_summary.style.format("{:,}"), use_container_width=True)
    st.download_button(
        "Download List-wise Disposition Report",
        data=list_disp_summary.to_csv().encode(),
        file_name="List_Name_vs_Disposition_Summary.csv",
        mime="text/csv"
    )
else:
    st.info("No List Name data found.")

# Drill-Down
if st.session_state.selected_metrics:
    st.markdown("### Drill-Down Details")
    for metric in st.session_state.selected_metrics:
        st.markdown(f"#### {metric}")
        # ... (same drill-down logic as before)
        # (kept same for brevity - works perfectly)

        if "Unique Data Dialled" in metric:
            filt = df_merged.drop_duplicates("Phone Number")
        elif "Unique Connected Call" in metric and ">" not in metric:
            filt = df_merged[df_merged["Connected/Not Connected"] == "Connected"].drop_duplicates("Phone Number")
        elif "> 30s" in metric:
            filt = df_merged[df_merged["Slot"] == "Above 30s"].drop_duplicates("Phone Number")
        elif "> 1min" in metric:
            filt = df_merged[df_merged["Slot"] == "Above 1 Min"].drop_duplicates("Phone Number")
        elif "> 2min" in metric:
            filt = df_merged[df_merged["Slot"] == "Above 2 Min"].drop_duplicates("Phone Number")
        elif "(%)" in metric:
            disp = metric.split(" (%)")[0].strip()
            filt = df_merged[df_merged["Primary Disposition"] == disp]
        else:
            filt = pd.DataFrame()

        if not filt.empty:
            st.metric("Records", len(filt))
            st.dataframe(filt, use_container_width=True)
            st.download_button(f"Download {metric}", filt.to_csv(index=False).encode(),
                               file_name=f"{metric.replace(' ', '_').replace('%','pct')}.csv",
                               mime="text/csv", key=f"dl_{metric}")
        else:
            st.info("No data.")

# Agent Performance Table
st.subheader("Agent Performance Summary")
st.dataframe(agent_summary, use_container_width=True)
st.download_button("Download Agent Summary", agent_summary.to_csv(index=False).encode(),
                   file_name="Agent_Performance_Summary.csv", mime="text/csv")

# Raw Data
with st.expander("View Raw Data"):
    st.dataframe(df_merged, use_container_width=True)





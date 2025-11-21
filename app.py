import pandas as pd
import streamlit as st

# ------------------- Page Config -------------------
st.set_page_config(page_title="Call Analytics Dashboard", layout="wide")
st.title("Call Data Analytics Dashboard")

# ------------------- Session State Initialization -------------------
required_keys = ["df", "df2", "df_merged", "summary", "agent_summary"]
for key in required_keys:
    if key not in st.session_state:
        st.session_state[key] = None

# This is the fix: selected_metrics is ALWAYS a set (never None)
if "selected_metrics" not in st.session_state:
    st.session_state.selected_metrics = set()   # ← Critical fix

# ------------------- Sidebar -------------------
with st.sidebar:
    st.header("Upload Files")
    uploaded_calling = st.file_uploader("Upload Calling.csv", type=["csv"], key="calling")

    if st.button("Clear All Data & Reset", type="primary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.session_state.selected_metrics = set()
        st.success("All data cleared!")
        st.rerun()

# ------------------- Process Files -------------------
if uploaded_calling:
    try:
        df = pd.read_csv(uploaded_calling)
        df2 = pd.read_csv("Disposition_.csv")

        # Cleaning
        df["Sub Sub Disposition"] = (
            df["Sub Sub Disposition"]
            .replace("", pd.NA)
            .fillna(df["Disposition"])
            .fillna(df["Dialer Status"])
        )

        df["Talk Sec"] = pd.to_timedelta(df["Talk Sec"], errors='coerce').dt.total_seconds().fillna(0)

        def slot_category(seconds):
            if seconds == 0: return "No Interaction"
            elif seconds < 30: return "Below 30s"
            elif seconds < 60: return "Above 30s"
            elif seconds < 120: return "Above 1 Min"
            else: return "Above 2 Min"

        df["Slot"] = df["Talk Sec"].apply(slot_category)

        df_merged = pd.merge(df, df2, left_on="Sub Sub Disposition", right_on="Call Disposed Status", how="left")

        # Summary Metrics
        unique_data_dialled = df_merged["Phone Number"].nunique()
        unique_connected = df_merged[df_merged["Connected/Not Connected"] == "Connected"]["Phone Number"].nunique()
        unique_gt_30s = df_merged[df_merged["Slot"] == "Above 30s"]["Phone Number"].nunique()
        unique_gt_1min = df_merged[df_merged["Slot"] == "Above 1 Min"]["Phone Number"].nunique()
        unique_gt_2min = df_merged[df_merged["Slot"] == "Above 2 Min"]["Phone Number"].nunique()
        connect_percent = (unique_connected / unique_data_dialled) * 100 if unique_data_dialled > 0 else 0

        def pct(val): return round((val / unique_connected) * 100, 2) if unique_connected > 0 else 0

        sdw_count = df_merged[df_merged["Primary Disposition"] == "SDW"].shape[0]
        lost_count = df_merged[df_merged["Primary Disposition"] == "Lost"].shape[0]
        fw_count = df_merged[df_merged["Primary Disposition"] == "Follow Up"].shape[0]
        vp_count = df_merged[df_merged["Primary Disposition"] == "Virtual Meet Proposed"].shape[0]
        vc_count = df_merged[df_merged["Primary Disposition"] == "Virtual Meet Confirmed"].shape[0]

        summary = pd.DataFrame({
            "Metric": [
                "Unique Data Dialled",
                "Unique Connected Call",
                "Unique Connected Call > 30s",
                "Unique Connected Call > 1min",
                "Unique Connected Call > 2min",
                "Connect %",
                "SDW (%)", "Lost (%)", "Follow Up (%)", "Virtual Meet Proposed (%)", "Virtual Meet Confirmed (%)"
            ],
            "Value": [
                unique_data_dialled, unique_connected, unique_gt_30s, unique_gt_1min, unique_gt_2min,
                f"{round(connect_percent, 2)}%",
                f"{pct(sdw_count)}%", f"{pct(lost_count)}%", f"{pct(fw_count)}%", f"{pct(vp_count)}%", f"{pct(vc_count)}%"
            ]
        })

        # Agent Summary with ALL Primary Dispositions as columns
        agent_base = df_merged.groupby("Agent Name").agg(
            Total_Calls=("Phone Number", "nunique"),
            Connected_GT_30s=("Slot", lambda x: (x == "Above 30s").sum()),
            Connected_GT_1min=("Slot", lambda x: (x == "Above 1 Min").sum()),
            Connected_GT_2min=("Slot", lambda x: (x == "Above 2 Min").sum()),
        ).reset_index()

        disposition_pivot = df_merged.groupby(["Agent Name", "Primary Disposition"]).size().unstack(fill_value=0).reset_index()

        agent_summary = pd.merge(agent_base, disposition_pivot, on="Agent Name", how="left")
        agent_summary.fillna(0, inplace=True)
        disp_cols = [c for c in agent_summary.columns if c not in agent_base.columns]
        agent_summary[disp_cols] = agent_summary[disp_cols].astype(int)

        # Positive & Ratio
        pos_list = ["Follow Up", "Virtual Meet Proposed", "Virtual Meet Confirmed"]
        agent_summary["Positive"] = agent_summary[[c for c in pos_list if c in agent_summary.columns]].sum(axis=1)
        agent_summary["Effort_to_Positive"] = agent_summary.apply(
            lambda r: round(r["Total_Calls"] / r["Positive"], 2) if r["Positive"] > 0 else None, axis=1
        )

        # Reorder columns
        base_cols = ["Agent Name", "Total_Calls", "Connected_GT_30s", "Connected_GT_1min", "Connected_GT_2min", "Positive", "Effort_to_Positive"]
        other_cols = sorted([c for c in agent_summary.columns if c not in base_cols])
        agent_summary = agent_summary[base_cols + other_cols]

        # Save to session state
        st.session_state.df_merged = df_merged
        st.session_state.summary = summary
        st.session_state.agent_summary = agent_summary

        st.success("Data processed successfully!")

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Please upload Calling.csv to begin.")
    st.stop()

# ================================= DASHBOARD =================================
df_merged = st.session_state.df_merged
summary = st.session_state.summary
agent_summary = st.session_state.agent_summary

st.subheader("Summary Metrics")

# Interactive checkbox table (this line now works because selected_metrics is always a set)
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

# Update selection
new_selection = set(edited[edited["Select"]]["Metric"])
if new_selection != st.session_state.selected_metrics:
    st.session_state.selected_metrics = new_selection
    st.rerun()

# Drill-down
if st.session_state.selected_metrics:
    st.markdown("### Drill-Down Details")
    for metric in st.session_state.selected_metrics:
        st.markdown(f"#### {metric}")

        if "Unique Data Dialled" in metric:
            filtered = df_merged.drop_duplicates("Phone Number")
        elif "Unique Connected Call" in metric and ">" not in metric:
            filtered = df_merged[df_merged["Connected/Not Connected"] == "Connected"].drop_duplicates("Phone Number")
        elif "> 30s" in metric:
            filtered = df_merged[df_merged["Slot"] == "Above 30s"].drop_duplicates("Phone Number")
        elif "> 1min" in metric:
            filtered = df_merged[df_merged["Slot"] == "Above 1 Min"].drop_duplicates("Phone Number")
        elif "> 2min" in metric:
            filtered = df_merged[df_merged["Slot"] == "Above 2 Min"].drop_duplicates("Phone Number")
        elif "(%)" in metric:
            disp = metric.split(" (%)")[0]
            filtered = df_merged[df_merged["Primary Disposition"] == disp]
        else:
            filtered = pd.DataFrame()

        if not filtered.empty:
            st.metric("Records", len(filtered))
            st.dataframe(filtered, use_container_width=True)
            st.download_button(
                label=f"Download {metric}",
                data=filtered.to_csv(index=False).encode(),
                file_name=f"{metric.replace(' ', '_').replace('(', '').replace(')', '').replace('%', 'pct')}.csv",
                mime="text/csv",
                key=f"dl_{metric}"
            )
        else:
            st.info("No records found.")
else:
    st.info("Select one or more metrics above to view details.")

# Agent Summary
st.subheader("Agent Performance Summary (All Dispositions)")
st.dataframe(agent_summary, use_container_width=True)
st.download_button(
    label="Download Agent Summary",
    data=agent_summary.to_csv(index=False).encode(),
    file_name="Agent_Summary_Full.csv",
    mime="text/csv"
)

with st.expander("View Full Merged Data"):
    st.dataframe(df_merged, use_container_width=True)

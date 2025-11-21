import pandas as pd
import streamlit as st

# ------------------- Page Config -------------------
st.set_page_config(page_title="Call Analytics Dashboard", layout="wide")
st.title("Call Data Analytics Dashboard")

# ------------------- Initialize Session State -------------------
for key in ["df", "df2", "df_merged", "summary", "selected_metric", "agent_summary"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ------------------- Sidebar: Upload & Clear -------------------
with st.sidebar:
    st.header("Upload Files")
    uploaded_calling = st.file_uploader("Upload Calling.csv", type=["csv"], key="calling")
    

    if st.button("Clear All Data & Reset", type="primary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.success("All data cleared!")
        st.experimental_rerun()

# ------------------- Process Uploaded Files -------------------
if uploaded_calling :
    try:
        df = pd.read_csv(uploaded_calling)
        df2 = pd.read_csv("Disposition_.csv")

        # Data Cleaning & Processing
        df["Sub Sub Disposition"] = (
            df["Sub Sub Disposition"]
            .replace("", pd.NA)
            .fillna(df["Disposition"])
            .fillna(df["Dialer Status"])
        )

        df["Talk Sec"] = pd.to_timedelta(df["Talk Sec"], errors='coerce').dt.total_seconds().fillna(0)

        def slot_category(seconds):
            if seconds == 0:
                return "No Interaction"
            elif seconds < 30:
                return "Below 30s"
            elif seconds < 60:
                return "Above 30s"
            elif seconds < 120:
                return "Above 1 Min"
            else:
                return "Above 2 Min"

        df["Slot"] = df["Talk Sec"].apply(slot_category)

        df_merged = pd.merge(
            df, df2,
            left_on="Sub Sub Disposition",
            right_on="Call Disposed Status",
            how="left"
        )

        # Calculations for summary metrics
        unique_data_dialled = df_merged["Phone Number"].nunique()
        unique_connected = df_merged[df_merged["Connected/Not Connected"] == "Connected"]["Phone Number"].nunique()
        unique_gt_30s = df_merged[df_merged["Slot"] == "Above 30s"]["Phone Number"].nunique()
        unique_gt_1min = df_merged[df_merged["Slot"] == "Above 1 Min"]["Phone Number"].nunique()
        unique_gt_2min = df_merged[df_merged["Slot"] == "Above 2 Min"]["Phone Number"].nunique()
        connect_percent = (unique_connected / unique_data_dialled) * 100 if unique_data_dialled > 0 else 0

        sdw_count = df_merged[df_merged["Primary Disposition"] == "SDW"].shape[0]
        sdw2_count = (sdw_count/unique_connected) * 100 
        lost_count = df_merged[df_merged["Primary Disposition"] == "Lost"].shape[0]
        fw_count = df_merged[df_merged["Primary Disposition"] == "Follow Up"].shape[0]
        fw2_count = (fw_count/unique_connected) * 100
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
                "SDW", "Follow Up","Lost" ,"Virtual Meet Proposed", "Virtual Meet Confirmed"
            ],
            "Value": [
                unique_data_dialled, unique_connected, unique_gt_30s,
                unique_gt_1min, unique_gt_2min, round(connect_percent, 2),
                sdw2_count, fw2_count,lost_count, vp_count, vc_count
            ]
        })

        # ------------------- Agent Summary -------------------
        agent_summary = df_merged.groupby("Agent Name").agg(
            Total_Calls=("Phone Number", "nunique"),
            Connected_GT_30s=("Slot", lambda x: ((x == "Above 30s") & (df_merged.loc[x.index, "Connected/Not Connected"] == "Connected")).sum()),
            Positive=("Primary Disposition", lambda x: x.isin(["Follow Up", "Virtual Meet Proposed", "Virtual Meet Confirmed"]).sum())
        ).reset_index()

        agent_summary["Effort_to_Positive"] = agent_summary.apply(
            lambda row: round(row["Total_Calls"] / row["Positive"], 2) if row["Positive"] > 0 else None, axis=1
        )

        st.session_state.df_merged = df_merged
        st.session_state.summary = summary
        st.session_state.agent_summary = agent_summary

        

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Please upload both CSV files to begin.")
    st.stop()

# ------------------- MAIN DASHBOARD -------------------
df_merged = st.session_state.df_merged
summary = st.session_state.summary
agent_summary = st.session_state.agent_summary

st.subheader("Summary Metrics (Select a row to drill down)")

# ------------------- Add Checkbox Column for Selection -------------------
summary_display = summary.copy()
summary_display["Select"] = False

edited_summary = st.data_editor(
    summary_display,
    use_container_width=True,
    hide_index=False,
    key="summary_editor",
    column_config={
        "Select": st.column_config.CheckboxColumn("Select", help="Click to view details")
    }
)

selected_rows = edited_summary[edited_summary["Select"] == True]
st.session_state.selected_metric = selected_rows.iloc[0]["Metric"] if not selected_rows.empty else None

# ------------------- Drill-Down Filtered Data -------------------
if st.session_state.selected_metric:
    metric = st.session_state.selected_metric
    st.markdown(f"### Showing records for: **{metric}**")

    filtered_df = pd.DataFrame()

    if metric == "Unique Data Dialled":
        filtered_df = df_merged.drop_duplicates("Phone Number")
    elif metric == "Unique Connected Call":
        filtered_df = df_merged[df_merged["Connected/Not Connected"] == "Connected"].drop_duplicates("Phone Number")
    elif metric == "Unique Connected Call > 30s":
        filtered_df = df_merged[df_merged["Slot"] == "Above 30s"].drop_duplicates("Phone Number")
    elif metric == "Unique Connected Call > 1min":
        filtered_df = df_merged[df_merged["Slot"] == "Above 1 Min"].drop_duplicates("Phone Number")
    elif metric == "Unique Connected Call > 2min":
        filtered_df = df_merged[df_merged["Slot"] == "Above 2 Min"].drop_duplicates("Phone Number")
    elif metric == "SDW":
        filtered_df = df_merged[df_merged["Primary Disposition"] == "SDW"]
    elif metric == "Follow Up":
        filtered_df = df_merged[df_merged["Primary Disposition"] == "Follow Up"]
    elif metric == "Virtual Meet Proposed":
        filtered_df = df_merged[df_merged["Primary Disposition"] == "Virtual Meet Proposed"]
    elif metric == "Virtual Meet Confirmed":
        filtered_df = df_merged[df_merged["Primary Disposition"] == "Virtual Meet Confirmed"]

    if not filtered_df.empty:
        st.metric(label=f"Total Records for {metric}", value=len(filtered_df))
        st.dataframe(filtered_df, use_container_width=True)

        csv_filtered = filtered_df.to_csv(index=False).encode()
        st.download_button(
            label=f"Download {metric} Data",
            data=csv_filtered,
            file_name=f"{metric.replace(' ', '_')}.csv",
            mime="text/csv"
        )
    else:
        st.warning("No records found for this metric.")
else:
    st.info("Select any row in the summary table above to see detailed records.")

# ------------------- Agent Summary Display -------------------
st.subheader("Agent Summary")
st.dataframe(agent_summary, use_container_width=True)

csv_agent = agent_summary.to_csv(index=False).encode()
st.download_button(
    label="Download Agent Summary",
    data=csv_agent,
    file_name="Agent_Summary.csv",
    mime="text/csv"
)

# Optional: Show full merged data
with st.expander("View Full Merged Data"):
    st.dataframe(df_merged, use_container_width=True)

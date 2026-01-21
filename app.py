import pandas as pd
import streamlit as st
import altair as alt
import matplotlib as plt
from datetime import datetime

# ------------------- Page Config -------------------
st.set_page_config(
    page_title="Call Analytics Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={'About': 'Unique Phone Number Analytics Dashboard'}
)

# Custom CSS for better look
st.markdown("""
<style>
    .main-header {font-size: 2.5rem; color: #1e3a8a; font-weight: bold; margin-bottom: 1rem;}
    .sub-header {font-size: 1.8rem; color: #1e40af; margin: 1.5rem 0 1rem;}
    .metric-card {background-color: #f8fafc; padding: 1rem; border-radius: 10px; border-left: 5px solid #0068c9;}
    .stButton>button {width: 100%;}
    .sidebar .sidebar-content {background-color: #f0f7ff;}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='main-header'>Call Analytics Dashboard</h1>", unsafe_allow_html=True)
st.markdown("<p style='color:#64748b; font-size:1.1rem;'>Unique Phone Number Analysis – Best Call Retained (Longest Talk Time)</p>", unsafe_allow_html=True)

# ------------------- Session State Initialization -------------------
for key in ["df_merged", "df_unique", "summary", "agent_summary", "list_disposition_summary", "selected_metrics"]:
    if key not in st.session_state:
        st.session_state[key] = None

if st.session_state.selected_metrics is None:
    st.session_state.selected_metrics = set()

# ------------------- Sidebar -------------------
with st.sidebar:
    st.header("Upload & Configuration")
    
    uploaded_calling = st.file_uploader("Upload **Calling.csv**", type=["csv"], key="calling")
    
    if uploaded_calling is None:
        st.info("Upload Calling.csv to begin analysis")
        st.stop()

    if st.button("Clear Cache & Reset Dashboard", type="primary", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.session_state.selected_metrics = set()
        st.success("Cache cleared!")
        st.rerun()

    st.markdown("---")
    st.subheader("Filters")

    # We'll apply filters after data load

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

    df["Talk Sec"] = pd.to_timedelta(df["Talk Sec"], errors='coerce').dt.total_seconds().fillna(0).astype(float)
    df["Call Start Time"] = pd.to_datetime(df["Call Start Time"], errors='coerce')
    df["Call Date"] = df["Call Start Time"].dt.date
    df["Hour"] = df["Call Start Time"].dt.hour

    def slot_category(sec):
        if sec == 0: return "No Interaction"
        elif sec < 30: return "Below 30s"
        elif sec < 60: return "30s–1min"
        elif sec < 120: return "1–2min"
        else: return "Above 2 Min"
    df["Slot"] = df["Talk Sec"].apply(slot_category)

    df_merged = pd.merge(df, df2, left_on="Sub Sub Disposition", right_on="Call Disposed Status", how="left")
    
    # Keep only BEST call per phone (longest talk time)
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

    summary_data = {
        "Unique Data Dialled": f"{total_dialled:,}",
        "Unique Connected": f"{unique_connected:,}",
        "Unique Connected >30s": f"{gt_30s:,}",
        "Unique Connected >1min": f"{gt_1min:,}",
        "Unique Connected >2min": f"{gt_2min:,}",
        "Connect %": f"{connect_pct}%",
        "SDW (%)": f"{pct(sdw)}%",
        "Lost (%)": f"{pct(lost)}%",
        "Follow Up (%)": f"{pct(fw)}%",
        "Virtual Meet Proposed (%)": f"{pct(vp)}%",
        "Virtual Meet Confirmed (%)": f"{pct(vc)}%",
        "Total Positive (%)": f"{pct(positive_total)}%"
    }

    # Agent Summary
    agent_base = df_unique.groupby("Agent Name").agg(
        Unique_Contacts=("Phone Number", "count"),
        Unique_Connected_GT30s=("Slot", lambda x: x.isin(["30s–1min", "1–2min", "Above 2 Min"]).sum()),
        Unique_Connected_GT1min=("Slot", lambda x: x.isin(["1–2min", "Above 2 Min"]).sum()),
        Unique_Connected_GT2min=("Slot", lambda x: (x == "Above 2 Min").sum())
    ).reset_index()

    positive_count = df_unique[df_unique["Primary Disposition"].isin(positive_dispositions)] \
        .groupby("Agent Name").size().reset_index(name="Positive_Outcomes")

    agent_summary = pd.merge(agent_base, positive_count, on="Agent Name", how="left").fillna(0)
    agent_summary["Positive_Outcomes"] = agent_summary["Positive_Outcomes"].astype(int)
    agent_summary["Effort_to_Positive"] = (agent_summary["Unique_Contacts"] / agent_summary["Positive_Outcomes"]).round(2)
    agent_summary["Effort_to_Positive"] = agent_summary["Effort_to_Positive"].replace([float('inf')], "-")

    disp_pivot = df_unique.pivot_table(index="Agent Name", columns="Primary Disposition", aggfunc='size', fill_value=0).reset_index()
    agent_summary = pd.merge(agent_summary, disp_pivot, on="Agent Name", how="left").fillna(0)

    # List-wise
    if "List Name" in df_unique.columns and df_unique["List Name"].notna().any():
        list_disp = df_unique.groupby(["List Name", "Primary Disposition"]).size().unstack(fill_value=0)
        list_disp["Total_Unique"] = list_disp.sum(axis=1)
        list_disp["Positive"] = list_disp.get("Follow Up", 0) + list_disp.get("Virtual Meet Proposed", 0) + list_disp.get("Virtual Meet Confirmed", 0)
        list_disp["Positive_%"] = (list_disp["Positive"] / list_disp["Total_Unique"] * 100).round(2)
        list_disp_summary = list_disp.sort_values("Total_Unique", ascending=False)
    else:
        list_disp_summary = pd.DataFrame()

    return summary_data, agent_summary, list_disp_summary


# ------------------- Load & Process Data -------------------
@st.cache_data(show_spinner=False)
def load_and_process(uploaded_file):
    df_calling = pd.read_csv(uploaded_file)
    df_merged, df_unique = process_data(df_calling)
    return df_merged, df_unique

if uploaded_calling:
    with st.spinner("Processing data – deduplicating by phone number..."):
        df_merged, df_unique_original = load_and_process(uploaded_calling)

    df_unique = df_unique_original.copy()

    # ------------------- Sidebar Filters -------------------
    with st.sidebar:
        col1, col2 = st.columns(2)
        min_date = pd.to_datetime(df_unique["Call Date"]).min().date()
        max_date = pd.to_datetime(df_unique["Call Date"]).max().date()
        with col1:
            start_date = st.date_input("From", min_date, min_value=min_date, max_value=max_date)
        with col2:
            end_date = st.date_input("To", max_date, min_value=min_date, max_value=max_date)

        if start_date > end_date:
            st.error("Start date cannot be after end date")
            st.stop()

        df_unique = df_unique[
            (pd.to_datetime(df_unique["Call Date"]) >= pd.to_datetime(start_date)) &
            (pd.to_datetime(df_unique["Call Date"]) <= pd.to_datetime(end_date))
        ]

        if "List Name" in df_unique.columns and df_unique["List Name"].notna().any():
            lists = ["All Lists"] + sorted(df_unique["List Name"].dropna().unique().tolist())
            chosen_list = st.selectbox("Filter by List", lists, index=0)
            if chosen_list != "All Lists":
                df_unique = df_unique[df_unique["List Name"] == chosen_list]

    # Generate metrics
    summary_data, agent_summary, list_disp_summary = generate_metrics(df_unique)

    # Save to session
    st.session_state.df_unique = df_unique
    st.session_state.summary = summary_data
    st.session_state.agent_summary = agent_summary
    st.session_state.list_disposition_summary = list_disp_summary

    st.success(f"Analysis Complete • {len(df_unique):,} Unique Phone Numbers")

else:
    st.info("Please upload **Calling.csv** to start.")
    st.stop()


# ================================= CLEAN DASHBOARD =================================

df_unique = st.session_state.df_unique
summary_data = st.session_state.summary
agent_summary = st.session_state.agent_summary
list_disp_summary = st.session_state.list_disposition_summary

# ------------------- KPI Cards -------------------
st.markdown("<h2 class='sub-header'>Key Performance Indicators</h2>", unsafe_allow_html=True)

cols = st.columns(5)
metrics_order = [
    ("Unique Data Dialled", "#0068c9"),
    ("Unique Connected", "#2ecc71"),
    ("Unique Connected >1min", "#ff6b6b"),
    ("Connect %","#0068c9"),
    ("Total Positive (%)", "#9b59b6"),
    ("Follow Up (%)", "#efe560"),
    ("Virtual Meet Proposed (%)", "#25e8ec"),
    ("Virtual Meet Confirmed (%)", "#ec6a1a")
]

for i, (label, color) in enumerate(metrics_order):
    with cols[i % 5]:
        value = summary_data[label]
        st.markdown(f"""
        <div style="background:{color}10; padding:20px; border-radius:12px; border-left:6px solid {color}; text-align:center;">
            <p style="margin:0; color:{color}; font-size:0.9rem;">{label}</p>
            <h2 style="margin:5px 0 0; color:{color};">{value}</h2>
        </div>
        """, unsafe_allow_html=True)
        if st.button(f"Drill → {label}", key=f"drill_{i}", use_container_width=True):
            st.session_state.selected_metrics = {label}
            st.rerun()

# ------------------- Tabs for Clean Navigation -------------------
tab1, tab2, tab3, tab4 = st.tabs(["Hourly Trend", "Top Agents", "List Performance", "Agent Leaderboard"])

with tab1:
    st.markdown("#### Unique Customers Reached by Hour of Day")
    hourly = df_unique.groupby("Hour").size().reset_index(name="Count")
    chart = alt.Chart(hourly).mark_area(
        color="#0068c9", opacity=0.8, line={'color': '#003087'}
    ).encode(
        x=alt.X("Hour:O", title="Hour"),
        y=alt.Y("Count:Q", title="Unique Phones Dialled"),
        tooltip=["Hour", "Count"]
    ).properties(height=400)
    st.altair_chart(chart, use_container_width=True)

with tab2:
    st.markdown("#### Top 10 Agents by Positive Outcomes")
    top10 = agent_summary.nlargest(10, "Positive_Outcomes")
    
    col1, col2 = st.columns([2,3])
    with col1:
        st.dataframe(
            top10[["Agent Name", "Unique_Contacts", "Positive_Outcomes", "Effort_to_Positive"]],
            use_container_width=True,
            hide_index=True
        )
    with col2:
        bar = alt.Chart(top10).mark_bar(cornerRadiusTopRight=8, cornerRadiusBottomRight=8, color="#27ae60").encode(
            y=alt.Y("Agent Name:N", sort="-x", title=""),
            x=alt.X("Positive_Outcomes:Q", title="Positive Outcomes"),
            tooltip=[alt.Tooltip("Agent Name"), "Positive_Outcomes", "Unique_Contacts", "Effort_to_Positive"]
        ).properties(height=400)
        st.altair_chart(bar, use_container_width=True)

with tab3:
    st.markdown("#### List-wise Performance (Unique Phones)")
    if not list_disp_summary.empty:
        styled = list_disp_summary.style \
            .format("{:,}") \
            .background_gradient(cmap="Greens", subset=["Total_Unique", "Positive", "Positive_%"]) \
            .bar(subset=["Positive_%"], color='#90EE90')
        st.dataframe(styled, use_container_width=True)
        
        csv = list_disp_summary.to_csv().encode()
        st.download_button(
            "Download List Report (CSV)",
            data=csv,
            file_name="list_performance_unique.csv",
            mime="text/csv"
        )
    else:
        st.info("No List Name column found in data.")

with tab4:
    st.markdown("#### Full Agent Performance Report")
    st.dataframe(agent_summary, use_container_width=True)
    csv_agent = agent_summary.to_csv(index=False).encode()
    st.download_button(
        "Download Full Agent Report",
        data=csv_agent,
        file_name="agent_performance_unique.csv",
        mime="text/csv"
    )

# ------------------- Drill-Down Section -------------------
# ==================== HELPER FUNCTION FOR DRILL-DOWN ====================
def get_filtered_data(metric_name, df):
    if "Unique Data Dialled" in metric_name:
        return df
    elif "Unique Connected" in metric_name and ">" not in metric_name:
        return df[df["Connected/Not Connected"] == "Connected"]
    elif ">30s" in metric_name:
        return df[df["Slot"].isin(["30s–1min", "1–2min", "Above 2 Min"])]
    elif ">1min" in metric_name:
        return df[df["Slot"].isin(["1–2min", "Above 2 Min"])]
    elif ">2min" in metric_name:
        return df[df["Slot"] == "Above 2 Min"]
    elif "(%)" in metric_name:
        disp = metric_name.split(" (")[0].strip()
        return df[df["Primary Disposition"] == disp]
    else:
        return pd.DataFrame()

# ==================== DRILL-DOWN SECTION ====================
if st.session_state.selected_metrics:
    st.markdown("---")
    st.markdown("<h2 style='color:#c2410c; text-align:center;'>Drill-Down Analysis</h2>", unsafe_allow_html=True)
    
    for metric in st.session_state.selected_metrics:
        filtered_df = get_filtered_data(metric, df_unique)
        record_count = len(filtered_df)
        
        with st.expander(f"{metric} → {record_count:,} Unique Records", expanded=True):
            if record_count > 0:
                st.metric("Total Records in This View", f"{record_count:,}")
                st.dataframe(filtered_df, use_container_width=True)
                
                csv = filtered_df.to_csv(index=False).encode()
                st.download_button(
                    label=f"Download {metric} Data",
                    data=csv,
                    file_name=f"{metric.replace(' ', '_').replace('%', 'pct')}.csv",
                    mime="text/csv",
                    key=f"download_{metric}"
                )
            else:
                st.info("No records match this filter.")

    # Clear selection button
    if st.button("Clear Drill-Down Selection", type="secondary"):
        st.session_state.selected_metrics = set()
        st.rerun()


# ==================== RAW DATA (Optional) ====================
with st.expander("Raw Unique Data – One Row Per Phone Number (Best Call Kept)"):
    st.write(f"**Total Unique Phone Numbers:** {len(df_unique):,}")
    st.dataframe(df_unique, use_container_width=True)
    
    csv_all = df_unique.to_csv(index=False).encode()
    st.download_button(
        "Download Full Raw Unique Data",
        data=csv_all,
        file_name="Unique_Phone_Numbers_Best_Call_Raw.csv",
        mime="text/csv"
    )







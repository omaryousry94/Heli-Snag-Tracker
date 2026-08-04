import streamlit as st
from supabase import create_client, Client
import pandas as pd
import time
import io

# Page Configuration for Mobile
st.set_page_config(page_title="Heli Snag Tracker", page_icon="🚁", layout="wide")

# Initialize Supabase Connection
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

st.title("🚁 Helicopter Live Snag Log")

# Sidebar - User Info & Quick Filters
st.sidebar.header("Engineer Details")
current_engineer = st.sidebar.text_input("Your Name / ID", value="Engineer")

st.sidebar.markdown("---")
st.sidebar.header("Filter Snags")
status_filter = st.sidebar.multiselect("Status", ["Open", "In Progress", "Deferred", "Closed"], default=["Open", "In Progress", "Deferred"])

# Navigation Tabs
tab1, tab2, tab3 = st.tabs(["📋 Active Dashboard", "➕ Log New Snag", "✏️ Update / Close Snag"])

# Defined Fleet List (Update tail numbers here as needed)
FLEET_TAIL_NUMBERS = [
    "AW139 - Reg 01",
    "AW139 - Reg 02",
    "AW169 - Reg 01",
    "AW169 - Reg 02",
    "B412 - Reg 01",
    "B412 - Reg 02"
]

# Defined System / ATA Chapters
ATA_CHAPTERS = [
    "Airframe / Structure",
    "Engine / Powerplant",
    "Hydraulic System",
    "Avionics / Instruments",
    "Rotor System / Transmission",
    "Electrical System",
    "Fuel System",
    "Flight Controls"
]

# ---------------------------------------------------------
# TAB 1: LIVE DASHBOARD
# ---------------------------------------------------------
with tab1:
    st.subheader("Current Fleet Status")

    # Search controls
    search_col1, search_col2 = st.columns(2)
    with search_col1:
        search_query = st.text_input("🔍 Search Description, ATA, or Engineer", placeholder="e.g. leak, generator, AW139...")
    with search_col2:
        aircraft_filter = st.multiselect("Filter Aircraft", FLEET_TAIL_NUMBERS, default=[])

    response = supabase.table("snags").select("*").order("id", desc=True).execute()
    data = response.data

    if data:
        df = pd.DataFrame(data)

        # Apply Status Filter
        if status_filter:
            df = df[df['status'].isin(status_filter)]

        # Apply Aircraft Filter
        if aircraft_filter:
            df = df[df['aircraft'].isin(aircraft_filter)]

        # Apply Keyword Search Filter
        if search_query.strip():
            q = search_query.lower()
            df = df[
                df['description'].astype(str).str.lower().str.contains(q) |
                df['system'].astype(str).str.lower().str.contains(q) |
                df['engineer'].astype(str).str.lower().str.contains(q) |
                df['aircraft'].astype(str).str.lower().str.contains(q)
            ]

        if not df.empty:
            open_count = len(df[df['status'] == 'Open'])
            st.metric(label="Open / Active Snags (Filtered)", value=open_count)

            # Display formatted table
            display_df = df[['id', 'created_at', 'aircraft', 'system', 'status', 'engineer', 'description', 'image_url', 'resolution']]
            st.dataframe(
                display_df,
                column_config={"image_url": st.column_config.LinkColumn("Photo", display_text="View Photo")},
                use_container_width=True,
                hide_index=True
            )

            # Photo Gallery View for mobile
            with st.expander("🖼️ View Photos of Selected Snags"):
                snags_with_photos = [s for s in df.to_dict('records') if s.get('image_url')]
                if snags_with_photos:
                    for s in snags_with_photos:
                        st.caption(f"**ID #{s['id']} - {s['aircraft']} ({s['system']})** logged by {s['engineer']}")
                        st.image(s['image_url'], width=300)
                else:
                    st.write("No photo attachments in the current filter selection.")

            # --- EXPORT SECTION ---
            st.markdown("---")
            st.subheader("📥 Export Data for Maintenance Handover")
            exp_col1, exp_col2 = st.columns(2)

            # CSV Export Button
            csv_data = df.to_csv(index=False).encode('utf-8')
            exp_col1.download_button(
                label="📄 Download Filtered Logs (CSV)",
                data=csv_data,
                file_name=f"heli_snag_report_{int(time.time())}.csv",
                mime="text/csv"
            )

            # Excel Export Button
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Snags')
            excel_data = buffer.getvalue()

            exp_col2.download_button(
                label="📊 Download Filtered Logs (Excel)",
                data=excel_data,
                file_name=f"heli_snag_report_{int(time.time())}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        else:
            st.info("No snags match the current search filters.")
    else:
        st.info("No snags recorded yet.")

# ---------------------------------------------------------
# TAB 2: LOG NEW SNAG (WITH CAMERA/PHOTO UPLOAD)
# ---------------------------------------------------------
with tab2:
    st.subheader("Report a Defect")

    with st.form("new_snag_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            aircraft = st.selectbox("Helicopter Tail Number", FLEET_TAIL_NUMBERS)
            system = st.selectbox("System / ATA Chapter", ATA_CHAPTERS)

        with col2:
            engineer = st.text_input("Logged By", value=current_engineer)
            status = st.selectbox("Initial Status", ["Open", "Deferred"])

        description = st.text_area("Detailed Snag Description", placeholder="Describe defect, leakage rates, fault codes, or inspection findings...")

        # Camera / Photo Upload Field
        uploaded_file = st.file_uploader("Take Photo or Attach Image", type=["jpg", "jpeg", "png"])

        submitted = st.form_submit_button("Submit Snag Entry")

        if submitted:
            if not description.strip():
                st.error("Please enter a description of the snag.")
            else:
                image_url = None

                # Upload image to Supabase Storage if attached
                if uploaded_file is not None:
                    file_bytes = uploaded_file.read()
                    file_path = f"snag_{int(time.time())}_{uploaded_file.name}"

                    supabase.storage.from_("snag-photos").upload(file_path, file_bytes)
                    image_url = supabase.storage.from_("snag-photos").get_public_url(file_path)

                new_entry = {
                    "aircraft": aircraft,
                    "system": system,
                    "engineer": engineer,
                    "status": status,
                    "description": description,
                    "image_url": image_url
                }

                supabase.table("snags").insert(new_entry).execute()
                st.success(f"Snag logged successfully for {aircraft}!")
                st.rerun()

# ---------------------------------------------------------
# TAB 3: UPDATE / CLOSE SNAG
# ---------------------------------------------------------
with tab3:
    st.subheader("Update Existing Snag Status")

    response = supabase.table("snags").select("*").neq("status", "Closed").execute()
    active_snags = response.data

    if active_snags:
        snag_options = {f"ID #{s['id']} - {s['aircraft']} ({s['system']}): {s['description'][:30]}...": s for s in active_snags}
        selected_label = st.selectbox("Select Snag to Update", list(snag_options.keys()))
        selected_snag = snag_options[selected_label]

        with st.form("update_snag_form"):
            st.write(f"**Current Details:** {selected_snag['description']}")
            if selected_snag.get('image_url'):
                st.image(selected_snag['image_url'], width=250, caption="Attached Defect Photo")

            new_status = st.selectbox("New Status", ["Open", "In Progress", "Deferred", "Closed"], index=["Open", "In Progress", "Deferred", "Closed"].index(selected_snag['status']))
            resolution = st.text_area("Corrective Action / Resolution Notes", value=selected_snag.get('resolution', ''))

            update_btn = st.form_submit_button("Save Update")

            if update_btn:
                supabase.table("snags").update({
                    "status": new_status,
                    "resolution": resolution
                }).eq("id", selected_snag['id']).execute()

                st.success(f"Snag ID #{selected_snag['id']} updated successfully!")
                st.rerun()
    else:
        st.info("No active open snags available to update.")

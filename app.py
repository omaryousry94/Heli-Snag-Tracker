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

# Helper function to fetch live fleet tail numbers from Supabase
def get_fleet_tail_numbers():
    try:
        res = supabase.table("fleet").select("tail_number").order("id").execute()
        if res.data:
            return [row["tail_number"] for row in res.data]
    except Exception:
        pass
    # Fallback default fleet list
    return [
        "AW139 - Reg 01", "AW139 - Reg 02",
        "AW169 - Reg 01", "AW169 - Reg 02",
        "B412 - Reg 01", "B412 - Reg 02"
    ]

# Fetch dynamic fleet list
FLEET_TAIL_NUMBERS = get_fleet_tail_numbers()

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

# Sidebar - User Info & Quick Filters
st.sidebar.header("Engineer Details")
current_engineer = st.sidebar.text_input("Your Name / ID", value="Engineer")

st.sidebar.markdown("---")
st.sidebar.header("Filter Snags")
status_filter = st.sidebar.multiselect("Status", ["Open", "In Progress", "Deferred", "Closed"], default=["Open", "In Progress", "Deferred"])

# Navigation Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📋 Dashboard", "➕ Log New Snag", "✏️ Update Snag", "🔒 Admin Controls"])

# ---------------------------------------------------------
# TAB 1: LIVE DASHBOARD & EXPORT
# ---------------------------------------------------------
with tab1:
    st.subheader("Current Fleet Status")

    search_col1, search_col2 = st.columns(2)
    with search_col1:
        search_query = st.text_input("🔍 Search Description, ATA, or Engineer", placeholder="e.g. leak, generator...")
    with search_col2:
        aircraft_filter = st.multiselect("Filter Aircraft", FLEET_TAIL_NUMBERS, default=[])

    response = supabase.table("snags").select("*").order("id", desc=True).execute()
    data = response.data

    if data:
        df = pd.DataFrame(data)

        if status_filter:
            df = df[df['status'].isin(status_filter)]
        if aircraft_filter:
            df = df[df['aircraft'].isin(aircraft_filter)]
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

            display_df = df[['id', 'created_at', 'aircraft', 'system', 'status', 'engineer', 'description', 'image_url', 'resolution']]
            st.dataframe(
                display_df,
                column_config={"image_url": st.column_config.LinkColumn("Photo", display_text="View Photo")},
                use_container_width=True,
                hide_index=True
            )

            with st.expander("🖼️ View Photos of Selected Snags"):
                snags_with_photos = [s for s in df.to_dict('records') if s.get('image_url')]
                if snags_with_photos:
                    for s in snags_with_photos:
                        st.caption(f"**ID #{s['id']} - {s['aircraft']}** logged by {s['engineer']}")
                        st.image(s['image_url'], width=300)
                else:
                    st.write("No photo attachments in the current filter selection.")

            # EXPORT SECTION
            st.markdown("---")
            st.subheader("📥 Export Data")
            exp_col1, exp_col2 = st.columns(2)

            csv_data = df.to_csv(index=False).encode('utf-8')
            exp_col1.download_button(
                label="📄 Download Logs (CSV)",
                data=csv_data,
                file_name=f"heli_snag_report_{int(time.time())}.csv",
                mime="text/csv"
            )

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Snags')
            excel_data = buffer.getvalue()

            exp_col2.download_button(
                label="📊 Download Logs (Excel)",
                data=excel_data,
                file_name=f"heli_snag_report_{int(time.time())}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("No snags match the current search filters.")
    else:
        st.info("No snags recorded yet.")

# ---------------------------------------------------------
# TAB 2: LOG NEW SNAG
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

        description = st.text_area("Detailed Snag Description")
        uploaded_file = st.file_uploader("Take Photo or Attach Image", type=["jpg", "jpeg", "png"])
        submitted = st.form_submit_button("Submit Snag Entry")

        if submitted:
            if not description.strip():
                st.error("Please enter a description.")
            else:
                image_url = None
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
# TAB 3: UPDATE SNAG
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
                st.image(selected_snag['image_url'], width=250)

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

# ---------------------------------------------------------
# TAB 4: ADMIN CONTROLS (FLEET MANAGEMENT & PURGING)
# ---------------------------------------------------------
with tab4:
    st.subheader("Admin Access Required")

    try:
        admin_secret = st.secrets["ADMIN_PASSWORD"]
    except KeyError:
        st.error("Admin Password not configured. Please add 'ADMIN_PASSWORD' to your Streamlit Secrets.")
        st.stop()

    admin_password = st.text_input("Enter Admin Password", type="password")

    if admin_password == admin_secret:
        st.success("Admin Access Granted")
        st.markdown("---")

        admin_sub1, admin_sub2 = st.tabs(["🚁 Fleet Management", "🗑️ Delete / Force Close Snags"])

        # --- SUBTAB 1: FLEET MANAGEMENT ---
        with admin_sub1:
            st.write("### Manage Fleet Registrations / Tail Numbers")

            col_add, col_rem = st.columns(2)

            with col_add:
                st.markdown("#### Add New Helicopter")
                new_tail = st.text_input("Enter Tail Number / Registration", placeholder="e.g. AW139 - Reg 03")
                if st.button("➕ Add to Fleet"):
                    if new_tail.strip():
                        try:
                            supabase.table("fleet").insert({"tail_number": new_tail.strip()}).execute()
                            st.success(f"Added {new_tail.strip()} to fleet!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error adding tail number: {e}")
                    else:
                        st.warning("Please type a valid tail number.")

            with col_rem:
                st.markdown("#### Remove Helicopter")
                tail_to_remove = st.selectbox("Select Tail Number to Remove", FLEET_TAIL_NUMBERS)
                if st.button("❌ Remove from Fleet"):
                    try:
                        supabase.table("fleet").delete().eq("tail_number", tail_to_remove).execute()
                        st.warning(f"Removed {tail_to_remove} from active fleet!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error removing tail number: {e}")

        # --- SUBTAB 2: DELETE / FORCE CLOSE SNAGS ---
        with admin_sub2:
            st.write("### Manage Database Records")

            response = supabase.table("snags").select("*").execute()
            all_snags = response.data

            if all_snags:
                admin_snag_options = {f"ID #{s['id']} [{s['status']}] - {s['aircraft']}: {s['description'][:30]}...": s for s in all_snags}
                del_selected_label = st.selectbox("Select Snag Record", list(admin_snag_options.keys()))
                admin_selected_snag = admin_snag_options[del_selected_label]

                del_col1, del_col2 = st.columns(2)

                with del_col1:
                    if st.button("❌ Permanently Delete Record"):
                        supabase.table("snags").delete().eq("id", admin_selected_snag['id']).execute()
                        st.warning(f"Snag ID #{admin_selected_snag['id']} deleted from database.")
                        st.rerun()

                with del_col2:
                    if st.button("✅ Force Close Snag"):
                        supabase.table("snags").update({"status": "Closed"}).eq("id", admin_selected_snag['id']).execute()
                        st.success(f"Snag ID #{admin_selected_snag['id']} forced to Closed status.")
                        st.rerun()
            else:
                st.info("The database is currently empty.")

    elif admin_password != "":
        st.error("Incorrect Password.")

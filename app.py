import streamlit as st
from supabase import create_client, Client
import pandas as pd
import time
import io
from PIL import Image
import plotly.express as px

# Page Configuration for Mobile
st.set_page_config(page_title="Heli Snag Tracker", page_icon="🚁", layout="wide")

# Initialize Supabase Connection
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# Helper function to delete image from Supabase Storage bucket
def delete_snag_photo_from_storage(image_url):
    if not image_url or not isinstance(image_url, str) or not image_url.strip():
        return
    try:
        # Extract filename from public URL (e.g. ".../snag-photos/snag_1690000.jpg" -> "snag_1690000.jpg")
        file_path = image_url.split('/')[-1]
        if file_path:
            supabase.storage.from_("snag-photos").remove([file_path])
    except Exception as e:
        st.warning(f"Could not remove image from storage: {e}")

# Helper function to fetch authorized engineers list
def get_authorized_engineers():
    try:
        res = supabase.table("authorized_engineers").select("engineer_name").order("engineer_name").execute()
        if res.data:
            return [row["engineer_name"] for row in res.data]
    except Exception:
        pass
    return []

# ---------------------------------------------------------
# INITIAL SESSION STATE & QUERY PARAMETER LOGIN RETRIEVAL
# ---------------------------------------------------------
if "engineer_name" not in st.session_state:
    st.session_state["engineer_name"] = ""
if "user_authenticated" not in st.session_state:
    st.session_state["user_authenticated"] = False
if "switch_user_mode" not in st.session_state:
    st.session_state["switch_user_mode"] = False
if "snag_added_success_msg" not in st.session_state:
    st.session_state["snag_added_success_msg"] = None

# Fetch remembered user directly from Streamlit URL Query Params
saved_user = st.query_params.get("remembered_user", None)

try:
    SITE_USER_PASSWORD = st.secrets["USER_PASSWORD"]
except KeyError:
    st.error("Site User Password not configured. Please add 'USER_PASSWORD' to your Streamlit Secrets.")
    st.stop()

# ---------------------------------------------------------
# LOGIN PROMPT LOGIC
# ---------------------------------------------------------
if not st.session_state["user_authenticated"]:
    st.title("🚁 Helicopter Live Snag Log")
    authorized_list = get_authorized_engineers()

    # SCENARIO A: Saved engineer remembered -> Ask Password Only
    if saved_user and not st.session_state["switch_user_mode"]:
        st.info(f"👋 Welcome back! Are you **{saved_user}**?")

        with st.form("quick_login_form"):
            input_pass = st.text_input("Enter Site Access Password", type="password")
            submit_quick = st.form_submit_button("Log In")

            if submit_quick:
                if input_pass.strip() != SITE_USER_PASSWORD.strip():
                    st.error("Incorrect Password.")
                else:
                    st.session_state["engineer_name"] = saved_user
                    st.session_state["user_authenticated"] = True
                    st.rerun()

        if st.button("Not you? Switch Engineer Profile"):
            st.session_state["switch_user_mode"] = True
            st.rerun()

    # SCENARIO B: First-time login OR "Switch Engineer" clicked
    else:
        st.info("👋 Welcome! Select your authorized engineer name/ID and site password.")

        with st.form("user_login_form"):
            input_name = st.text_input("Engineer Name / ID", placeholder="e.g. John Doe / ENG-102")
            input_pass = st.text_input("Site Access Password", type="password")
            remember_me = st.checkbox("Remember my name on this device", value=True)
            submit_login = st.form_submit_button("Log In")

            if submit_login:
                clean_name = input_name.strip() if input_name else ""
                clean_pass = input_pass.strip()

                if not clean_name:
                    st.error("Please enter a valid Engineer Name or ID.")
                elif clean_pass != SITE_USER_PASSWORD.strip():
                    st.error("Incorrect Site Access Password.")
                else:
                    target_name = clean_name.title()
                    if authorized_list:
                        auth_lower_map = {name.lower(): name for name in authorized_list}
                        if clean_name.lower() in auth_lower_map:
                            target_name = auth_lower_map[clean_name.lower()]
                        else:
                            st.error("Access Denied: Your name is not on the authorized engineers list.")
                            st.stop()

                    st.session_state["engineer_name"] = target_name
                    st.session_state["user_authenticated"] = True
                    st.session_state["switch_user_mode"] = False

                    if remember_me:
                        st.query_params["remembered_user"] = target_name

                    st.rerun()

        if saved_user and st.session_state["switch_user_mode"]:
            if st.button("Back to Quick Login"):
                st.session_state["switch_user_mode"] = False
                st.rerun()

    st.stop()  # Halts further rendering until authenticated

# ---------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------
st.title("🚁 Helicopter Live Snag Log")

def compress_image(uploaded_file, max_size=(1024, 1024), quality=75):
    image = Image.open(uploaded_file)
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    image.thumbnail(max_size)
    output_buffer = io.BytesIO()
    image.save(output_buffer, format="JPEG", quality=quality, optimize=True)
    return output_buffer.getvalue()

def get_fleet_tail_numbers():
    try:
        res = supabase.table("fleet").select("tail_number").order("id").execute()
        if res.data:
            return [row["tail_number"] for row in res.data]
    except Exception:
        pass
    return [
        "AW139 - Reg 01", "AW139 - Reg 02",
        "AW169 - Reg 01", "AW169 - Reg 02",
        "B412 - Reg 01", "B412 - Reg 02"
    ]

FLEET_TAIL_NUMBERS = get_fleet_tail_numbers()

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
st.sidebar.write(f"Logged in as: **{st.session_state['engineer_name']}**")
if st.sidebar.button("Log Out / Switch Engineer"):
    st.session_state["engineer_name"] = ""
    st.session_state["user_authenticated"] = False
    st.session_state["switch_user_mode"] = True
    if "remembered_user" in st.query_params:
        del st.query_params["remembered_user"]
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("Filter Snags")
status_filter = st.sidebar.multiselect("Status", ["Open", "In Progress", "Deferred", "Closed"], default=["Open", "In Progress", "Deferred"])

# Navigation Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 Dashboard", "➕ Log New Snag", "✏️ Update Snag", "📊 Analytics", "🔒 Admin Controls"])

# ---------------------------------------------------------
# TAB 1: LIVE DASHBOARD & EXPORT
# ---------------------------------------------------------
with tab1:
    header_col1, header_col2 = st.columns([3, 1])
    with header_col1:
        st.subheader("Current Fleet Status")
    with header_col2:
        if st.button("🔄 Refresh Live Data", use_container_width=True):
            st.rerun()

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

            display_df = df[['id', 'aircraft', 'system', 'status', 'engineer', 'description', 'image_url', 'resolution', 'created_at']]
            st.dataframe(
                display_df,
                column_config={"image_url": st.column_config.LinkColumn("Photo", display_text="View Photo")},
                use_container_width=True,
                hide_index=True
            )

            st.markdown("---")
            with st.expander("🖼️ Inspect Photo Attachment"):
                snags_with_photos = [
                    s for s in df.to_dict('records')
                    if s.get('image_url') and pd.notna(s.get('image_url')) and str(s.get('image_url')).strip() != ""
                ]
                if snags_with_photos:
                    photo_options = {
                        f"ID #{s['id']} - [{s['aircraft']}] {s['description'][:40]}...": s
                        for s in snags_with_photos
                    }
                    selected_photo_label = st.selectbox(
                        "Select a snag record to display its photo:",
                        list(photo_options.keys())
                    )
                    chosen_snag = photo_options[selected_photo_label]

                    st.caption(f"**Photo for Snag ID #{chosen_snag['id']}** | {chosen_snag['aircraft']} ({chosen_snag['system']}) logged by {chosen_snag['engineer']}")
                    st.image(chosen_snag['image_url'], width=450)
                else:
                    st.info("No photo attachments in the current filter selection.")

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

    if st.session_state["snag_added_success_msg"]:
        st.success(st.session_state["snag_added_success_msg"])
        st.session_state["snag_added_success_msg"] = None  # Clear after display

    with st.form("new_snag_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            aircraft = st.selectbox("Helicopter Tail Number", FLEET_TAIL_NUMBERS)
            system = st.selectbox("System / ATA Chapter", ATA_CHAPTERS)
        with col2:
            engineer = st.text_input("Logged By", value=st.session_state["engineer_name"], disabled=True)
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
                    compressed_bytes = compress_image(uploaded_file, max_size=(1024, 1024), quality=75)
                    file_path = f"snag_{int(time.time())}.jpg"

                    supabase.storage.from_("snag-photos").upload(
                        path=file_path,
                        file=compressed_bytes,
                        file_options={"content-type": "image/jpeg", "upsert": "true"}
                    )
                    image_url = supabase.storage.from_("snag-photos").get_public_url(file_path)

                new_entry = {
                    "aircraft": aircraft,
                    "system": system,
                    "engineer": st.session_state["engineer_name"],
                    "status": status,
                    "description": description,
                    "image_url": image_url
                }
                supabase.table("snags").insert(new_entry).execute()

                st.session_state["snag_added_success_msg"] = f"✅ Snag successfully recorded and saved for {aircraft}!"
                st.rerun()

# ---------------------------------------------------------
# TAB 3: UPDATE SNAG
# ---------------------------------------------------------
with tab3:
    st.subheader("Update Existing Snag Status")

    response = supabase.table("snags").select("*").neq("status", "Closed").order("id", desc=True).execute()
    active_snags = response.data

    if active_snags:
        st.markdown("#### 1. Filter Snag Location")
        filter_col1, filter_col2 = st.columns(2)

        with filter_col1:
            selected_ac_filter = st.selectbox("Filter by Aircraft (A/C)", ["All Aircraft"] + FLEET_TAIL_NUMBERS)

        with filter_col2:
            selected_ata_filter = st.selectbox("Filter by ATA Chapter", ["All ATA Chapters"] + ATA_CHAPTERS)

        filtered_active = active_snags
        if selected_ac_filter != "All Aircraft":
            filtered_active = [s for s in filtered_active if s.get("aircraft") == selected_ac_filter]
        if selected_ata_filter != "All ATA Chapters":
            filtered_active = [s for s in filtered_active if s.get("system") == selected_ata_filter]

        st.markdown("---")
        st.markdown("#### 2. Select & Update Defect")

        if filtered_active:
            snag_options = {
                f"ID #{s['id']} | [{s['aircraft']}] [{s['system']}] - {s['description'][:35]}...": s
                for s in filtered_active
            }
            selected_label = st.selectbox("Select Snag to Update", list(snag_options.keys()))
            selected_snag = snag_options[selected_label]

            with st.form("update_snag_form"):
                col_info1, col_info2 = st.columns(2)
                col_info1.write(f"**Aircraft:** {selected_snag['aircraft']}")
                col_info1.write(f"**ATA Chapter:** {selected_snag['system']}")
                col_info2.write(f"**Logged By:** {selected_snag['engineer']}")
                col_info2.write(f"**Current Status:** `{selected_snag['status']}`")

                st.write(f"**Description:** {selected_snag['description']}")

                if selected_snag.get('image_url') and pd.notna(selected_snag.get('image_url')) and str(selected_snag.get('image_url')).strip() != "":
                    st.image(selected_snag['image_url'], width=300, caption="Attached Defect Photo")

                st.markdown("---")
                new_status = st.selectbox("New Status", ["Open", "In Progress", "Deferred", "Closed"], index=["Open", "In Progress", "Deferred", "Closed"].index(selected_snag['status']))
                resolution = st.text_area("Corrective Action / Maintenance Notes", value=selected_snag.get('resolution', ''))
                update_btn = st.form_submit_button("Save Update")

                if update_btn:
                    # DELETE PHOTO FROM STORAGE IF STATUS WAS CHANGED TO CLOSED
                    if new_status == "Closed" and selected_snag.get("image_url"):
                        delete_snag_photo_from_storage(selected_snag["image_url"])
                        updated_image_url = None
                    else:
                        updated_image_url = selected_snag.get("image_url")

                    supabase.table("snags").update({
                        "status": new_status,
                        "resolution": resolution,
                        "image_url": updated_image_url
                    }).eq("id", selected_snag['id']).execute()

                    st.success(f"Snag ID #{selected_snag['id']} updated successfully!")
                    st.rerun()
        else:
            st.info("No active open snags match the selected A/C and ATA Chapter filters.")
    else:
        st.info("No active open snags available to update.")

# ---------------------------------------------------------
# TAB 4: FLEET RELIABILITY ANALYTICS DASHBOARD
# ---------------------------------------------------------
with tab4:
    st.subheader("📈 Fleet Reliability & Defect Metrics")

    response_all = supabase.table("snags").select("*").execute()
    all_data = response_all.data

    if all_data:
        df_analytics = pd.DataFrame(all_data)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Recorded Snags", len(df_analytics))
        m2.metric("Open Snags", len(df_analytics[df_analytics['status'] == 'Open']))
        m3.metric("Deferred Snags", len(df_analytics[df_analytics['status'] == 'Deferred']))
        m4.metric("Closed Snags", len(df_analytics[df_analytics['status'] == 'Closed']))

        st.markdown("---")

        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            st.markdown("#### Defects by Aircraft Tail Number")
            ac_counts = df_analytics.groupby(['aircraft', 'status']).size().reset_index(name='count')
            fig_ac = px.bar(
                ac_counts,
                x='aircraft',
                y='count',
                color='status',
                title="Snags per Helicopter (by Status)",
                barmode='stack',
                template="plotly_dark"
            )
            st.plotly_chart(fig_ac, use_container_width=True)

        with col_chart2:
            st.markdown("#### System / ATA Chapter Breakdown")
            ata_counts = df_analytics['system'].value_counts().reset_index()
            ata_counts.columns = ['System', 'Count']
            fig_ata = px.pie(
                ata_counts,
                names='System',
                values='Count',
                title="Distribution of Defect Systems",
                hole=0.4,
                template="plotly_dark"
            )
            st.plotly_chart(fig_ata, use_container_width=True)

        st.markdown("---")

        st.markdown("#### Fleet Defect Matrix (A/C vs ATA Chapter)")
        pivot_df = df_analytics.pivot_table(index='system', columns='aircraft', aggfunc='size', fill_value=0)
        fig_heat = px.imshow(
            pivot_df,
            labels=dict(x="Aircraft Registration", y="ATA Chapter / System", color="Defect Count"),
            title="Defect Density Heatmap",
            color_continuous_scale="Reds",
            template="plotly_dark"
        )
        st.plotly_chart(fig_heat, use_container_width=True)

    else:
        st.info("No data available to build analytics charts yet.")

# ---------------------------------------------------------
# TAB 5: ADMIN CONTROLS
# ---------------------------------------------------------
with tab5:
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

        admin_sub1, admin_sub2, admin_sub3 = st.tabs(["👨‍🔧 Engineer User Control", "🚁 Fleet Management", "🗑️ Bulk Delete / Force Close Snags"])

        with admin_sub1:
            st.write("### Manage Authorized Engineers List")
            eng_col_add, eng_col_rem = st.columns(2)

            curr_engineers = get_authorized_engineers()

            with eng_col_add:
                st.markdown("#### Authorize New Engineer")
                new_eng_name = st.text_input("Engineer Full Name / ID", placeholder="e.g. John Doe / ENG-102")
                if st.button("➕ Grant Access"):
                    if new_eng_name.strip():
                        formatted_name = new_eng_name.strip().title()
                        try:
                            supabase.table("authorized_engineers").insert({"engineer_name": formatted_name}).execute()
                            st.success(f"Added '{formatted_name}' to authorized engineers!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error adding engineer (might already exist): {e}")
                    else:
                        st.warning("Please enter a valid engineer name.")

            with eng_col_rem:
                st.markdown("#### Revoke Engineer Access")
                if curr_engineers:
                    eng_to_remove = st.selectbox("Select Engineer to Revoke Access", curr_engineers)
                    if st.button("❌ Revoke Access"):
                        try:
                            supabase.table("authorized_engineers").delete().eq("engineer_name", eng_to_remove).execute()
                            st.warning(f"Revoked access for '{eng_to_remove}'.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error revoking access: {e}")
                else:
                    st.info("No authorized engineers in the list.")

        with admin_sub2:
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

        # MULTI-SELECT BULK DELETE / CLOSE
        with admin_sub3:
            st.write("### Bulk Manage Database Records")
            response = supabase.table("snags").select("*").order("id", desc=True).execute()
            all_snags = response.data

            if all_snags:
                st.info("Select one or multiple snag records below to perform bulk actions.")
                admin_snag_map = {
                    f"ID #{s['id']} [{s['status']}] - {s['aircraft']}: {s['description'][:35]}...": s
                    for s in all_snags
                }

                selected_labels = st.multiselect(
                    "Select Snag Records:",
                    options=list(admin_snag_map.keys()),
                    placeholder="Choose snags to modify or delete..."
                )

                if selected_labels:
                    selected_records = [admin_snag_map[lbl] for lbl in selected_labels]
                    selected_ids = [rec['id'] for rec in selected_records]
                    st.write(f"**Selected {len(selected_ids)} snag(s)** (IDs: {', '.join(map(str, selected_ids))})")

                    del_col1, del_col2 = st.columns(2)
                    with del_col1:
                        if st.button(f"❌ Delete {len(selected_ids)} Selected Record(s)", use_container_width=True):
                            # Remove all attached photos from storage first
                            for rec in selected_records:
                                if rec.get("image_url"):
                                    delete_snag_photo_from_storage(rec["image_url"])

                            supabase.table("snags").delete().in_("id", selected_ids).execute()
                            st.warning(f"Deleted {len(selected_ids)} snag record(s) and associated photo(s) from database.")
                            st.rerun()

                    with del_col2:
                        if st.button(f"✅ Force Close {len(selected_ids)} Selected Record(s)", use_container_width=True):
                            # Remove all attached photos from storage first
                            for rec in selected_records:
                                if rec.get("image_url"):
                                    delete_snag_photo_from_storage(rec["image_url"])

                            supabase.table("snags").update({"status": "Closed", "image_url": None}).in_("id", selected_ids).execute()
                            st.success(f"Force-closed {len(selected_ids)} snag record(s) and cleared photo storage.")
                            st.rerun()
                else:
                    st.caption("No snags selected yet. Click the box above to choose records.")
            else:
                st.info("The database is currently empty.")

    elif admin_password != "":
        st.error("Incorrect Password.")

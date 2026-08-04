import streamlit as st
from supabase import create_client, Client
import pandas as pd
import time

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

# ---------------------------------------------------------
# TAB 1: LIVE DASHBOARD
# ---------------------------------------------------------
with tab1:
    st.subheader("Current Fleet Status")
    
    response = supabase.table("snags").select("*").order("id", desc=True).execute()
    data = response.data
    
    if data:
        df = pd.DataFrame(data)
        
        if status_filter:
            df = df[df['status'].isin(status_filter)]
            
        if not df.empty:
            open_count = len(df[df['status'] == 'Open'])
            st.metric(label="Open / Active Snags", value=open_count)
            
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
                snags_with_photos = [s for s in data if s.get('image_url')]
                if snags_with_photos:
                    for s in snags_with_photos:
                        st.caption(f"**ID #{s['id']} - {s['aircraft']} ({s['system']})** logged by {s['engineer']}")
                        st.image(s['image_url'], width=300)
                else:
                    st.write("No photo attachments uploaded yet.")
        else:
            st.info("No snags match the selected filter.")
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
            aircraft = st.selectbox("Helicopter Tail Number", ["Heli-01", "Heli-02", "Heli-03", "Heli-04", "Heli-05", "Heli-06"])
            system = st.selectbox("System / ATA", ["Airframe", "Engine", "Hydraulics", "Avionics", "Rotor System", "Electrical", "Fuel"])
            
        with col2:
            engineer = st.text_input("Logged By", value=current_engineer)
            status = st.selectbox("Initial Status", ["Open", "Deferred"])
            
        description = st.text_area("Detailed Snag Description", placeholder="Describe the leak, warning light, or mechanical fault...")
        
        # Camera / Photo Upload Field
        uploaded_file = st.file_uploader("Take Photo or Attach Image", type=["jpg", "jpeg", "png"])
        
        submitted = st.form_submit_button("Submit Snag Entry")
        
        if submitted:
            if not description.strip():
                st.error("Please enter a description of the snag.")
            else:
                image_url = None
                
                # If an image was taken/uploaded, send it to Supabase Storage
                if uploaded_file is not None:
                    file_bytes = uploaded_file.read()
                    file_path = f"snag_{int(time.time())}_{uploaded_file.name}"
                    
                    # Upload file to Supabase Storage Bucket
                    supabase.storage.from_("snag-photos").upload(file_path, file_bytes)
                    
                    # Get public URL of the uploaded image
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

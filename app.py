import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import math

# ==================== PAGE CONFIG ====================
st.set_page_config(page_title="Nearest Wells Finder", layout="wide")

# ==================== THEME TOGGLE (Dark/Light) ====================
def apply_theme(theme):
    if theme == "Dark":
        st.markdown("""
        <style>
        .stApp {
            background-color: #0e1117;
            color: #ffffff;
        }
        .stSidebar {
            background-color: #262730;
            color: #ffffff;
        }
        .stSidebar .stSelectbox, .stSidebar .stNumberInput, .stSidebar .stFileUploader {
            color: #ffffff;
        }
        .stDataFrame {
            background-color: #1a1d23;
        }
        .stAlert {
            background-color: #2d313a;
        }
        .stMarkdown, .stText, .stTitle, .stHeader, .stSubheader {
            color: #ffffff !important;
        }
        div[data-testid="stMetricValue"] {
            color: #ffffff;
        }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
        .stApp {
            background-color: #ffffff;
            color: #000000;
        }
        .stSidebar {
            background-color: #f0f2f6;
            color: #000000;
        }
        .stSidebar .stSelectbox, .stSidebar .stNumberInput, .stSidebar .stFileUploader {
            color: #000000;
        }
        .stDataFrame {
            background-color: #ffffff;
        }
        .stMarkdown, .stText, .stTitle, .stHeader, .stSubheader {
            color: #000000 !important;
        }
        div[data-testid="stMetricValue"] {
            color: #000000;
        }
        </style>
        """, unsafe_allow_html=True)

# ==================== CRS FUNCTIONS ====================
@st.cache_resource
def get_transformer(source_epsg):
    try:
        # Always convert to WGS84 (EPSG:4326) for Folium maps
        return Transformer.from_crs(f"epsg:{source_epsg}", "epsg:4326", always_xy=True)
    except Exception as e:
        st.error(f"Invalid EPSG code or transformation error: {e}")
        return None

def utm_to_latlng(transformer, x, y):
    try:
        lon, lat = transformer.transform(x, y)
        return lat, lon
    except:
        return None, None

# ==================== DATA LOADING ====================
@st.cache_data
def load_sample_data():
    # Sample data matching the Excel example (WD-013 and neighbors)
    data = {
        'Well': [
            'WD-013', 'WD-068', 'WD-061', 'WD-164', 'WD-159',
            'WD-042', 'WD-083', 'WD-044', 'WD-015', 'WD-016',
            'WD-001', 'WD-002', 'WD-100', 'WD-200'
        ],
        'x': [
            8863112.854, 8863308.970, 8863274.206, 8863096.451, 8863003.079,
            8863143.511, 8863222.253, 8863326.177, 8866192.325, 8864937.506,
            8864561.000, 8864537.896, 8865385.633, 8865069.497
        ],
        'y': [
            6657796.548, 6657795.664, 6657957.022, 6658085.823, 6658132.314,
            6657407.359, 6658239.733, 6658220.555, 6657681.362, 6657700.648,
            6658132.000, 6658277.700, 6659601.586, 6657519.218
        ]
    }
    return pd.DataFrame(data)

def load_wells_file(uploaded_file):
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(uploaded_file, engine='openpyxl')
            else:
                df = pd.read_csv(uploaded_file)
            required_cols = ['Well', 'x', 'y']
            if all(col in df.columns for col in required_cols):
                return df
            else:
                st.error("Uploaded file must contain columns: Well, x, y")
                return None
        except Exception as e:
            st.error(f"Error reading file: {e}")
            return None
    return None

def load_polygon_file(uploaded_poly):
    if uploaded_poly is not None:
        try:
            if uploaded_poly.name.endswith(('.xlsx', '.xls')):
                df_poly = pd.read_excel(uploaded_poly, engine='openpyxl')
            else:
                df_poly = pd.read_csv(uploaded_poly)
            if 'x' in df_poly.columns and 'y' in df_poly.columns:
                return df_poly[['x', 'y']].values.tolist()
            else:
                st.error("Polygon file must contain columns: x, y")
                return None
        except Exception as e:
            st.error(f"Error reading polygon file: {e}")
            return None
    return None

# ==================== SIDEBAR UI ====================
with st.sidebar:
    st.header("⚙️ Settings")
    
    # ---- Theme Selection ----
    theme_choice = st.radio("🎨 Theme", ["Light", "Dark"], index=0)
    apply_theme(theme_choice)
    
    st.markdown("---")
    
    # ---- File Uploads ----
    uploaded_file = st.file_uploader("📂 Upload Wells File (Excel/CSV)", type=['xlsx', 'xls', 'csv'])
    uploaded_poly = st.file_uploader("📂 Upload Boundary Polygon (optional)", type=['xlsx', 'xls', 'csv'])
    
    st.markdown("---")
    
    # ---- CRS Selection ----
    st.subheader("🌍 Coordinate System (Source CRS)")
    crs_options = {
        "WGS 84 Geographic (EPSG:4326)": 4326,
        "WGS 84 / UTM Zone 36N (EPSG:32636)": 32636,
        "WGS 84 / UTM Zone 37N (EPSG:32637)": 32637,
        "Egypt 1907 / Red Belt (EPSG:22992)": 22992,
        "Egypt 1907 / Blue Belt (EPSG:22991)": 22991,
        "Egypt 1907 / Purple Belt (EPSG:22993)": 22993,
        "Egypt 1907 / Extended Purple (EPSG:22994)": 22994,
        "Custom EPSG Code": "custom"
    }
    
    selected_crs_label = st.selectbox(
        "Select Source CRS for your X/Y data:",
        list(crs_options.keys()),
        index=1  # Default to UTM 36N as it matches the sample data
    )
    
    if crs_options[selected_crs_label] == "custom":
        custom_epsg = st.number_input("Enter EPSG Code (e.g., 32636):", value=32636, step=1)
        source_epsg = int(custom_epsg)
    else:
        source_epsg = crs_options[selected_crs_label]
    
    st.caption(f"🔄 Converting from EPSG:{source_epsg} to WGS84 for map display.")
    
    st.markdown("---")
    
    # ---- Load Data ----
    if uploaded_file is not None:
        df = load_wells_file(uploaded_file)
        if df is None:
            st.stop()
    else:
        df = load_sample_data()
        st.info("💡 No file uploaded. Using sample data (similar to WD-013 example).")
    
    # Load polygon
    polygon_points = load_polygon_file(uploaded_poly)
    if polygon_points is None and uploaded_poly is not None:
        st.stop()
    
    if df is not None and not df.empty:
        well_list = df['Well'].tolist()
        selected_well = st.selectbox("🟢 Select a Well", well_list, index=0)
        search_radius = st.number_input("📏 Search Radius (meters)", min_value=0.0, value=500.0, step=50.0)
        search_clicked = st.button("🔍 Find Nearby Wells", use_container_width=True, type="primary")

# ==================== MAIN CONTENT ====================
if df is not None and not df.empty and search_clicked:
    selected_row = df[df['Well'] == selected_well]
    if selected_row.empty:
        st.error("Selected well not found!")
        st.stop()
    
    sel_x = selected_row['x'].values[0]
    sel_y = selected_row['y'].values[0]
    
    # Calculate Euclidean distances
    df['distance'] = np.sqrt((df['x'] - sel_x)**2 + (df['y'] - sel_y)**2)
    nearby_df = df[df['distance'] <= search_radius].copy()
    nearby_df = nearby_df.sort_values('distance').reset_index(drop=True)
    
    # ===== Results Display =====
    st.markdown(f"### ✅ Results for Well **{selected_well}**")
    col1, col2, col3 = st.columns(3)
    col1.metric("Number of Nearby Wells", len(nearby_df))
    if not nearby_df.empty:
        col2.metric("Closest Well", nearby_df.iloc[0]['Well'])
        col3.metric("Closest Distance", f"{nearby_df.iloc[0]['distance']:.2f} m")
    else:
        col2.metric("Closest Well", "-")
        col3.metric("Closest Distance", "-")
    
    # Table
    st.markdown("#### 📋 Nearby Wells Table")
    if not nearby_df.empty:
        st.dataframe(
            nearby_df[['Well', 'x', 'y', 'distance']].style.format({'distance': '{:.2f}'}),
            use_container_width=True
        )
    else:
        st.warning("No wells found within the specified radius.")
    
    # ===== Coordinate Transformation =====
    transformer = get_transformer(source_epsg)
    if transformer is None:
        st.stop()
    
    def convert_row(row):
        lat, lon = utm_to_latlng(transformer, row['x'], row['y'])
        return pd.Series([lat, lon], index=['lat', 'lon'])
    
    df_latlng = df.apply(convert_row, axis=1)
    df = pd.concat([df, df_latlng], axis=1)
    
    # Drop rows with failed conversion
    df = df.dropna(subset=['lat', 'lon'])
    if df.empty:
        st.error("Coordinate conversion failed for all wells. Check your CRS selection.")
        st.stop()
    
    center_lat = df[df['Well'] == selected_well]['lat'].values[0]
    center_lon = df[df['Well'] == selected_well]['lon'].values[0]
    
    # ===== MAP 1: General View =====
    st.markdown("#### 🗺️ General Map (All Wells + Boundary)")
    m1 = folium.Map(location=[center_lat, center_lon], zoom_start=12, control_scale=True)
    
    # Add Polygon Boundary
    if polygon_points:
        try:
            poly_latlng = []
            for x, y in polygon_points:
                lat, lon = utm_to_latlng(transformer, x, y)
                if lat is not None and lon is not None:
                    poly_latlng.append([lat, lon])
            if poly_latlng:
                folium.Polygon(
                    locations=poly_latlng,
                    color="green",
                    weight=3,
                    fill=True,
                    fill_color="green",
                    fill_opacity=0.15,
                    popup="Boundary Polygon"
                ).add_to(m1)
        except Exception as e:
            st.warning(f"Could not draw polygon: {e}")
    
    # Add search radius circle
    folium.Circle(
        location=[center_lat, center_lon],
        radius=search_radius,
        color='red',
        weight=2,
        fill=False,
        popup=f"Radius: {search_radius} m"
    ).add_to(m1)
    
    # Add wells
    for idx, row in df.iterrows():
        well_name = row['Well']
        dist = row['distance']
        
        if well_name == selected_well:
            color = 'red'
            icon_type = 'info-sign'
        elif dist <= search_radius:
            color = 'blue'
            icon_type = 'ok-sign'
        else:
            color = 'gray'
            icon_type = 'minus-sign'
        
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=f"{well_name}<br>Distance: {dist:.2f} m" if dist > 0 else f"{well_name} (Selected)",
            icon=folium.Icon(color=color, icon=icon_type, prefix='glyphicon')
        ).add_to(m1)
    
    st_folium(m1, width=1200, height=500, returned_objects=[])
    
    # ===== MAP 2: Zoom View =====
    st.markdown("#### 🔍 Zoom View (Selected + Nearby Wells Only)")
    nearby_wells = df[df['distance'] <= search_radius].copy()
    if selected_well not in nearby_wells['Well'].values:
        nearby_wells = pd.concat([nearby_wells, df[df['Well'] == selected_well]])
    
    if not nearby_wells.empty:
        center_lat_zoom = nearby_wells['lat'].mean()
        center_lon_zoom = nearby_wells['lon'].mean()
        
        m2 = folium.Map(location=[center_lat_zoom, center_lon_zoom], zoom_start=14, control_scale=True)
        
        # Add polygon to zoom map
        if polygon_points and poly_latlng:
            folium.Polygon(
                locations=poly_latlng,
                color="green",
                weight=2,
                fill=True,
                fill_color="green",
                fill_opacity=0.1
            ).add_to(m2)
        
        folium.Circle(
            location=[center_lat, center_lon],
            radius=search_radius,
            color='red',
            weight=2,
            fill=False
        ).add_to(m2)
        
        for idx, row in nearby_wells.iterrows():
            well_name = row['Well']
            color = 'red' if well_name == selected_well else 'blue'
            icon_type = 'info-sign' if well_name == selected_well else 'ok-sign'
            
            folium.Marker(
                location=[row['lat'], row['lon']],
                popup=f"{well_name}<br>Distance: {row['distance']:.2f} m",
                icon=folium.Icon(color=color, icon=icon_type, prefix='glyphicon')
            ).add_to(m2)
        
        st_folium(m2, width=1200, height=450, returned_objects=[])
    else:
        st.info("No nearby wells to zoom in on.")
    
    # ===== Download Results =====
    if not nearby_df.empty:
        csv = nearby_df[['Well', 'x', 'y', 'distance']].to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv,
            file_name='nearest_wells.csv',
            mime='text/csv',
        )

else:
    if not search_clicked:
        st.info("👈 Select a well and radius from the sidebar, then click 'Find Nearby Wells'.")

# ==================== FOOTER ====================
st.markdown("---")
st.caption("🔒 This app runs entirely locally. Your data never leaves your machine.")

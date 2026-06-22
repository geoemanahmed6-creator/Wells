import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import MeasureControl
from streamlit_folium import folium_static  # <-- الحل السحري بدلاً من st_folium
from pyproj import Transformer
import tempfile
import os

# ==================== PAGE CONFIG ====================
st.set_page_config(page_title="Nearest Wells Finder", layout="wide", initial_sidebar_state="expanded")

# ==================== GOOGLE FONTS (Poppins) ====================
st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# ==================== CUSTOM CSS (PROFESSIONAL UI) ====================
def apply_theme(theme):
    if theme == "Dark":
        st.markdown("""
        <style>
            /* Global */
            .stApp { background: #0b0e14; font-family: 'Poppins', sans-serif; }
            .stSidebar { background: linear-gradient(180deg, #161b24 0%, #0b0e14 100%); border-right: 1px solid #2a313c; }
            .stSidebar .stMarkdown, .stSidebar .stText, .stSidebar .stSelectbox, .stSidebar .stNumberInput { color: #e0e4e8; }
            
            /* Headers */
            h1, h2, h3, h4, .stTitle, .stHeader { color: #ffffff !important; font-weight: 600 !important; }
            
            /* Cards / Metrics */
            div[data-testid="stMetricValue"] { color: #f0b90b !important; font-size: 2.2rem !important; font-weight: 700; }
            div[data-testid="stMetricLabel"] { color: #a0aec0 !important; font-weight: 400; letter-spacing: 0.5px; }
            div[data-testid="stMetricDelta"] { color: #48bb78 !important; }
            
            /* Dataframe */
            .stDataFrame { background: #161b24; border-radius: 12px; border: 1px solid #2a313c; }
            .stDataFrame thead tr th { background: #1f2937 !important; color: #f0b90b !important; font-weight: 600; }
            .stDataFrame tbody tr td { color: #e2e8f0 !important; border-bottom: 1px solid #2a313c; }
            
            /* Buttons */
            .stButton > button {
                background: linear-gradient(90deg, #f0b90b, #d69e04);
                color: #0b0e14;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                padding: 0.6rem 1.5rem;
                box-shadow: 0 4px 15px rgba(240, 185, 11, 0.3);
                transition: all 0.3s ease;
            }
            .stButton > button:hover {
                transform: scale(1.02);
                box-shadow: 0 6px 20px rgba(240, 185, 11, 0.5);
                background: linear-gradient(90deg, #f5c421, #d69e04);
            }
            
            /* Captions & Info */
            .stCaption, .stAlert { color: #a0aec0; }
            .stInfo { background: #1f2937; border-left: 4px solid #f0b90b; }
            
            /* Spacing */
            .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
            /* Global */
            .stApp { background: #f8fafc; font-family: 'Poppins', sans-serif; }
            .stSidebar { background: linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%); border-right: 1px solid #e2e8f0; }
            .stSidebar .stMarkdown, .stSidebar .stText, .stSidebar .stSelectbox, .stSidebar .stNumberInput { color: #1e293b; }
            
            /* Headers */
            h1, h2, h3, h4, .stTitle, .stHeader { color: #0f172a !important; font-weight: 600 !important; }
            
            /* Cards / Metrics */
            div[data-testid="stMetricValue"] { color: #2563eb !important; font-size: 2.2rem !important; font-weight: 700; }
            div[data-testid="stMetricLabel"] { color: #475569 !important; font-weight: 400; letter-spacing: 0.5px; }
            
            /* Dataframe */
            .stDataFrame { background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
            .stDataFrame thead tr th { background: #f1f5f9 !important; color: #0f172a !important; font-weight: 600; }
            .stDataFrame tbody tr td { color: #1e293b !important; border-bottom: 1px solid #e2e8f0; }
            
            /* Buttons */
            .stButton > button {
                background: linear-gradient(90deg, #2563eb, #1d4ed8);
                color: #ffffff;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                padding: 0.6rem 1.5rem;
                box-shadow: 0 4px 15px rgba(37, 99, 235, 0.3);
                transition: all 0.3s ease;
            }
            .stButton > button:hover {
                transform: scale(1.02);
                box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5);
                background: linear-gradient(90deg, #3b82f6, #2563eb);
            }
            
            .stInfo { background: #eff6ff; border-left: 4px solid #2563eb; }
        </style>
        """, unsafe_allow_html=True)

# ==================== CRS FUNCTIONS ====================
@st.cache_resource
def get_transformer(source_epsg):
    try:
        return Transformer.from_crs(f"epsg:{source_epsg}", "epsg:4326", always_xy=True)
    except Exception as e:
        st.error(f"Invalid EPSG: {e}")
        return None

def utm_to_latlng(transformer, x, y):
    try:
        lon, lat = transformer.transform(x, y)
        return lat, lon
    except:
        return None, None

# ==================== UNIT CONVERSION ====================
def format_distance(dist_m, unit):
    if "Kilometers" in unit:
        return dist_m / 1000.0
    elif "Feet" in unit:
        return dist_m * 3.28084
    else:
        return dist_m

def get_unit_label(unit):
    if "Kilometers" in unit:
        return "km"
    elif "Feet" in unit:
        return "ft"
    else:
        return "m"

def get_measure_units(unit):
    if "Kilometers" in unit:
        return "kilometers", "meters"
    elif "Feet" in unit:
        return "feet", "meters"
    else:
        return "meters", "kilometers"

# ==================== DATA LOADING ====================
@st.cache_data
def load_sample_data():
    data = {
        'Well': ['WD-013', 'WD-068', 'WD-061'],
        'x': [8863112.854, 8863308.970, 8863274.206],
        'y': [6657796.548, 6657795.664, 6657957.022]
    }
    return pd.DataFrame(data)

def clean_numeric_column(series):
    series = series.astype(str)
    series = series.str.replace(r'[^\d\.\-]', '', regex=True)
    return pd.to_numeric(series, errors='coerce')

def load_wells_file(uploaded_file, y_shift):
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(uploaded_file, engine='openpyxl')
            else:
                df = pd.read_csv(uploaded_file)
            
            required_cols = ['Well', 'x', 'y']
            if not all(col in df.columns for col in required_cols):
                st.error("File must contain columns: Well, x, y")
                return None
            
            df['x'] = clean_numeric_column(df['x'])
            df['y'] = clean_numeric_column(df['y'])
            
            initial_len = len(df)
            df = df.dropna(subset=['x', 'y'])
            if len(df) < initial_len:
                st.warning(f"⚠️ {initial_len - len(df)} rows had invalid X/Y and were ignored.")
            
            if df.empty:
                st.error("No valid numeric data found.")
                return None
            
            df['y'] = df['y'] + y_shift
            return df
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
                df_poly['x'] = clean_numeric_column(df_poly['x'])
                df_poly['y'] = clean_numeric_column(df_poly['y'])
                df_poly = df_poly.dropna(subset=['x', 'y'])
                return df_poly[['x', 'y']].values.tolist()
            else:
                st.error("Polygon must have columns: x, y")
                return None
        except Exception as e:
            st.error(f"Polygon error: {e}")
            return None
    return None

# ==================== BUILD MAP (FIXED FOR STATIC DISPLAY) ====================
def build_map(center_lat, center_lon, zoom_start, df, selected_well, search_radius, polygon_points, transformer, unit, zoom_mode=False):
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles=None, control_scale=True)
    
    # 1. Tile Layers
    folium.TileLayer('OpenStreetMap', name='🗺️ Street Map', show=True).add_to(m)
    folium.TileLayer('OpenTopoMap', name='🏔️ Topographic', show=False).add_to(m)
    folium.TileLayer('CartoDB positron', name='🌐 Light Simple', show=False).add_to(m)
    folium.TileLayer('CartoDB dark_matter', name='🌑 Dark Simple', show=False).add_to(m)
    
    # 2. Measure Tool (RULER) - الآن سيظهر بالتأكيد مع folium_static
    primary, secondary = get_measure_units(unit)
    MeasureControl(
        position='topright',
        primary_length_unit=primary,
        secondary_length_unit=secondary,
        active_color='red',
        completed_color='#ff0000',
        toggle_display=True
    ).add_to(m)
    
    # 3. Polygon
    poly_latlng = []
    if polygon_points:
        try:
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
                    popup="Boundary"
                ).add_to(m)
        except:
            pass
    
    # 4. Search Radius
    folium.Circle(
        location=[center_lat, center_lon],
        radius=search_radius,
        color='red',
        weight=2,
        fill=False,
        popup=f"Radius: {search_radius} {get_unit_label(unit)}"
    ).add_to(m)
    
    # 5. Wells
    for idx, row in df.iterrows():
        well_name = row['Well']
        dist_m = row['distance']
        dist_formatted = format_distance(dist_m, unit)
        dist_label = get_unit_label(unit)
        x_val = row['x']
        y_val = row['y']
        
        if well_name == selected_well:
            color = 'red'
            icon_type = 'info-sign'
        elif dist_m <= search_radius:
            color = 'blue'
            icon_type = 'ok-sign'
        else:
            if zoom_mode:
                continue
            color = 'gray'
            icon_type = 'minus-sign'
        
        tooltip_text = f"""
        <b>Well:</b> {well_name}<br>
        <b>X:</b> {x_val:.2f}<br>
        <b>Y:</b> {y_val:.2f}<br>
        <b>Distance:</b> {dist_formatted:.3f} {dist_label}
        """
        tooltip = folium.Tooltip(tooltip_text, sticky=True)
        
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=f"<b>{well_name}</b>",
            tooltip=tooltip,
            icon=folium.Icon(color=color, icon=icon_type, prefix='glyphicon')
        ).add_to(m)
    
    # 6. Legend (Stylish)
    bg_color = '#161b24' if st.session_state.get('theme', 'Light') == 'Dark' else '#ffffff'
    text_color = '#e2e8f0' if st.session_state.get('theme', 'Light') == 'Dark' else '#1e293b'
    border_color = '#2a313c' if st.session_state.get('theme', 'Light') == 'Dark' else '#e2e8f0'
    
    legend_html = f'''
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000; 
                background: {bg_color}; padding: 8px 14px; 
                border-radius: 10px; border: 1px solid {border_color}; 
                font-size: 12px; font-family: 'Poppins', Arial; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                color: {text_color}; line-height: 1.8; backdrop-filter: blur(4px);">
        <b style="font-size:13px;">📍 Legend</b><br>
        <span style="color: #ef4444;">●</span> Selected Well<br>
        <span style="color: #3b82f6;">●</span> Nearby Well<br>
        <span style="color: #94a3b8;">●</span> Other Well<br>
        <span style="color: #22c55e; border: 1px solid #22c55e; padding: 0px 10px;">▬</span> Boundary
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # 7. Layer Control (Visible)
    folium.LayerControl(position='topright', collapsed=False).add_to(m)
    
    return m

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    
    theme_choice = st.radio("🎨 Theme", ["Light", "Dark"], index=0)
    st.session_state['theme'] = theme_choice
    apply_theme(theme_choice)
    
    st.markdown("---")
    
    uploaded_file = st.file_uploader("📂 Upload Wells", type=['xlsx', 'xls', 'csv'])
    uploaded_poly = st.file_uploader("📂 Upload Boundary (optional)", type=['xlsx', 'xls', 'csv'])
    
    st.markdown("---")
    st.subheader("🔧 Coordinate Correction")
    y_shift = st.number_input("➕ Y Offset (meters)", value=0.0, step=100000.0, format="%f")
    if y_shift != 0:
        st.success(f"✅ Y increased by {y_shift:,.0f} m")
    
    st.markdown("---")
    crs_options = {
        "WGS 84 / UTM Zone 36N (EPSG:32636)": 32636,
        "WGS 84 / UTM Zone 37N (EPSG:32637)": 32637,
        "Egypt 1907 / Red Belt (EPSG:22992)": 22992,
        "Egypt 1907 / Blue Belt (EPSG:22991)": 22991,
        "Egypt 1907 / Purple Belt (EPSG:22993)": 22993,
        "Egypt 1907 / Extended Purple (EPSG:22994)": 22994,
        "WGS 84 Geographic (EPSG:4326)": 4326,
        "Custom EPSG Code": "custom"
    }
    selected_crs_label = st.selectbox("🌍 Source CRS", list(crs_options.keys()), index=0)
    if crs_options[selected_crs_label] == "custom":
        custom_epsg = st.number_input("EPSG Code", value=32636, step=1)
        source_epsg = int(custom_epsg)
    else:
        source_epsg = crs_options[selected_crs_label]
    st.caption(f"🔄 Converting EPSG:{source_epsg} to WGS84")
    
    st.markdown("---")
    st.subheader("📏 Distance Unit")
    distance_unit = st.selectbox("Select unit:", ["Meters (m)", "Kilometers (km)", "Feet (ft)"], index=0)
    
    st.markdown("---")
    if uploaded_file is not None:
        df = load_wells_file(uploaded_file, y_shift)
        if df is None:
            st.stop()
    else:
        df = load_sample_data()
        st.info("💡 Using sample data.")
    
    polygon_points = load_polygon_file(uploaded_poly)
    if polygon_points is None and uploaded_poly is not None:
        st.stop()
    
    if df is not None and not df.empty:
        well_list = df['Well'].tolist()
        selected_well = st.selectbox("🟢 Select a Well", well_list, index=0)
        search_radius_m = st.number_input("📏 Search Radius (m)", min_value=0.0, value=500.0, step=50.0)
        search_clicked = st.button("🔍 Find Nearby Wells", use_container_width=True, type="primary")

# ==================== MAIN CONTENT ====================
if df is not None and not df.empty and search_clicked:
    selected_row = df[df['Well'] == selected_well]
    if selected_row.empty:
        st.error("Well not found!")
        st.stop()
    
    sel_x = selected_row['x'].values[0]
    sel_y = selected_row['y'].values[0]
    
    df['distance'] = np.sqrt((df['x'] - sel_x)**2 + (df['y'] - sel_y)**2)
    
    # Exclude the selected well itself
    nearby_df = df[(df['distance'] <= search_radius_m) & (df['Well'] != selected_well)].copy()
    nearby_df = nearby_df.sort_values('distance').reset_index(drop=True)
    
    unit_label = get_unit_label(distance_unit)
    nearby_df[f'Distance ({unit_label})'] = nearby_df['distance'].apply(lambda d: format_distance(d, distance_unit))
    
    # Professional Stats Cards
    st.markdown(f"### 🎯 Results for Well **{selected_well}**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📌 Nearby Wells", len(nearby_df))
    with col2:
        if not nearby_df.empty:
            st.metric("🏆 Closest Well", nearby_df.iloc[0]['Well'])
        else:
            st.metric("🏆 Closest Well", "-")
    with col3:
        if not nearby_df.empty:
            closest_dist = format_distance(nearby_df.iloc[0]['distance'], distance_unit)
            st.metric("📏 Closest Distance", f"{closest_dist:.3f} {unit_label}")
        else:
            st.metric("📏 Closest Distance", "-")
    
    st.markdown("---")
    
    # Table
    st.markdown("#### 📋 Nearby Wells Table")
    if not nearby_df.empty:
        display_cols = ['Well', 'x', 'y', f'Distance ({unit_label})']
        st.dataframe(
            nearby_df[display_cols].style.format({f'Distance ({unit_label})': '{:.3f}'}),
            use_container_width=True,
            height=300
        )
    else:
        st.warning("⚠️ No other wells found within the specified radius.")
    
    # Transformation
    transformer = get_transformer(source_epsg)
    if transformer is None:
        st.stop()
    
    def convert_row(row):
        lat, lon = utm_to_latlng(transformer, row['x'], row['y'])
        return pd.Series([lat, lon], index=['lat', 'lon'])
    
    df_latlng = df.apply(convert_row, axis=1)
    df = pd.concat([df, df_latlng], axis=1)
    df = df.dropna(subset=['lat', 'lon'])
    
    if df.empty:
        st.error("Conversion failed. Try a different CRS or Y Offset.")
        st.stop()
    
    center_lat = df[df['Well'] == selected_well]['lat'].values[0]
    center_lon = df[df['Well'] == selected_well]['lon'].values[0]
    
    # ===== MAP 1: General View =====
    st.markdown("#### 🗺️ General Map (All Wells)")
    st.caption("🖱️ Hover wells for details. 🧭 Use ruler (top-right) to measure distances. ☰ Layers icon to change map style.")
    
    m1 = build_map(
        center_lat=center_lat,
        center_lon=center_lon,
        zoom_start=12,
        df=df,
        selected_well=selected_well,
        search_radius=search_radius_m,
        polygon_points=polygon_points,
        transformer=transformer,
        unit=distance_unit,
        zoom_mode=False
    )
    # استخدمي folium_static بدلاً من st_folium
    folium_static(m1, width=1200, height=550)
    
    # ===== MAP 2: Zoom View =====
    st.markdown("#### 🔍 Zoom View (Selected + Nearby Wells)")
    nearby_wells = df[(df['distance'] <= search_radius_m) & (df['Well'] != selected_well)].copy()
    nearby_wells = pd.concat([nearby_wells, df[df['Well'] == selected_well]])
    
    if not nearby_wells.empty:
        center_lat_zoom = nearby_wells['lat'].mean()
        center_lon_zoom = nearby_wells['lon'].mean()
        m2 = build_map(
            center_lat=center_lat_zoom,
            center_lon=center_lon_zoom,
            zoom_start=14,
            df=nearby_wells,
            selected_well=selected_well,
            search_radius=search_radius_m,
            polygon_points=polygon_points,
            transformer=transformer,
            unit=distance_unit,
            zoom_mode=True
        )
        folium_static(m2, width=1200, height=500)
    else:
        st.info("ℹ️ No nearby wells to zoom in on.")
    
    # ===== Download Buttons =====
    st.markdown("---")
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        if not nearby_df.empty:
            csv = nearby_df[['Well', 'x', 'y', f'Distance ({unit_label})']].to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Results CSV", data=csv, file_name='nearest_wells.csv', mime='text/csv', use_container_width=True)
    
    with col_dl2:
        # Export map as HTML
        html_path = tempfile.NamedTemporaryFile(delete=False, suffix='.html').name
        m1.save(html_path)
        with open(html_path, 'r', encoding='utf-8') as f:
            html_data = f.read()
        st.download_button("🗺️ Export Map as HTML", data=html_data, file_name='wells_map.html', mime='text/html', use_container_width=True)
        try:
            os.unlink(html_path)
        except:
            pass

else:
    if not search_clicked:
        st.info("👈 Select a well, set Y Offset if needed, then click 'Find Nearby Wells'.")

st.markdown("---")
st.caption("🔒 Local app. Data never leaves your machine. | 🖱️ Hover wells for details. | 🧭 Ruler + 4 map styles in top-right corner.")

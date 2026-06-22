import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import MeasureControl
from streamlit_folium import st_folium
from pyproj import Transformer
import tempfile
import os

# ==================== PAGE CONFIG ====================
st.set_page_config(page_title="Nearest Wells Finder", layout="wide")

# ==================== THEME TOGGLE ====================
def apply_theme(theme):
    if theme == "Dark":
        st.markdown("""
        <style>
        .stApp { background-color: #0e1117; color: #ffffff; }
        .stSidebar { background-color: #262730; color: #ffffff; }
        .stDataFrame { background-color: #1a1d23; }
        .stMarkdown, .stText, .stTitle, .stHeader { color: #ffffff !important; }
        div[data-testid="stMetricValue"] { color: #ffffff; }
        .stTable { color: #ffffff; }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
        .stApp { background-color: #ffffff; color: #000000; }
        .stSidebar { background-color: #f0f2f6; color: #000000; }
        .stDataFrame { background-color: #ffffff; }
        .stMarkdown, .stText, .stTitle, .stHeader { color: #000000 !important; }
        div[data-testid="stMetricValue"] { color: #000000; }
        .stTable { color: #000000; }
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
    else:  # Meters
        return dist_m

def get_unit_label(unit):
    if "Kilometers" in unit:
        return "km"
    elif "Feet" in unit:
        return "ft"
    else:
        return "m"

def get_measure_units(unit):
    """Return primary and secondary units for MeasureControl based on user selection"""
    if "Kilometers" in unit:
        return "kilometers", "meters"
    elif "Feet" in unit:
        return "feet", "meters"
    else:  # Meters
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

# ==================== BUILD MAP FUNCTION (UPDATED) ====================
def build_map(center_lat, center_lon, zoom_start, df, selected_well, search_radius, polygon_points, transformer, unit, zoom_mode=False):
    
    # Base map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles=None, control_scale=True)
    
    # ===== 1. TILE LAYERS (Multiple Views) =====
    folium.TileLayer('OpenStreetMap', name='🗺️ Street Map', show=True).add_to(m)
    folium.TileLayer('OpenTopoMap', name='🏔️ Topographic', show=False).add_to(m)
    folium.TileLayer('CartoDB positron', name='🌐 Light Simple', show=False).add_to(m)
    folium.TileLayer('CartoDB dark_matter', name='🌑 Dark Simple', show=False).add_to(m)
    
    # ===== 2. MEASURE TOOL (Ruler) with Dynamic Units =====
    primary, secondary = get_measure_units(unit)
    MeasureControl(
        position='topright',
        primary_length_unit=primary,
        secondary_length_unit=secondary,
        active_color='red',
        completed_color='#ff0000'
    ).add_to(m)
    
    # ===== 3. POLYGON BOUNDARY =====
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
                    popup="Boundary Polygon"
                ).add_to(m)
        except:
            pass
    
    # ===== 4. SEARCH RADIUS =====
    folium.Circle(
        location=[center_lat, center_lon],
        radius=search_radius,
        color='red',
        weight=2,
        fill=False,
        popup=f"Radius: {search_radius} {get_unit_label(unit)}"
    ).add_to(m)
    
    # ===== 5. WELLS WITH TOOLTIP (Hover) =====
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
            popup=f"<b>{well_name}</b><br>X: {x_val:.2f}<br>Y: {y_val:.2f}",
            tooltip=tooltip,
            icon=folium.Icon(color=color, icon=icon_type, prefix='glyphicon')
        ).add_to(m)
    
    # ===== 6. LEGEND (SMALLER - UPDATED) =====
    # Smaller font and padding
    bg_color = '#1a1d23' if st.session_state.get('theme', 'Light') == 'Dark' else 'white'
    text_color = 'white' if st.session_state.get('theme', 'Light') == 'Dark' else 'black'
    border_color = '#444' if st.session_state.get('theme', 'Light') == 'Dark' else '#ccc'
    
    legend_html = f'''
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000; 
                background: {bg_color}; padding: 6px 10px; 
                border-radius: 6px; border: 1px solid {border_color}; 
                font-size: 11px; font-family: Arial; 
                box-shadow: 1px 1px 6px rgba(0,0,0,0.2);
                color: {text_color}; line-height: 1.5;">
        <b>📍 Legend</b><br>
        <span style="color: red;">●</span> Selected Well<br>
        <span style="color: blue;">●</span> Nearby Well<br>
        <span style="color: gray;">●</span> Other Well<br>
        <span style="color: green; border: 1px solid green; padding: 0px 8px;">▬</span> Boundary
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # ===== 7. LAYER CONTROL =====
    folium.LayerControl().add_to(m)
    
    return m

# ==================== SIDEBAR UI ====================
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Theme
    theme_choice = st.radio("🎨 Theme", ["Light", "Dark"], index=0)
    st.session_state['theme'] = theme_choice
    apply_theme(theme_choice)
    
    st.markdown("---")
    
    # File uploads
    uploaded_file = st.file_uploader("📂 Upload Wells (Excel/CSV)", type=['xlsx', 'xls', 'csv'])
    uploaded_poly = st.file_uploader("📂 Upload Boundary (optional)", type=['xlsx', 'xls', 'csv'])
    
    st.markdown("---")
    
    # Y Offset
    st.subheader("🔧 Coordinate Correction")
    y_shift = st.number_input("➕ Y Offset (meters)", value=0.0, step=100000.0, format="%f")
    if y_shift != 0:
        st.success(f"✅ Y increased by {y_shift:,.0f} m")
    
    st.markdown("---")
    
    # CRS Selection
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
    
    selected_crs_label = st.selectbox("🌍 Source Coordinate System", list(crs_options.keys()), index=0)
    
    if crs_options[selected_crs_label] == "custom":
        custom_epsg = st.number_input("Enter EPSG Code", value=32636, step=1)
        source_epsg = int(custom_epsg)
    else:
        source_epsg = crs_options[selected_crs_label]
    
    st.caption(f"🔄 Converting from EPSG:{source_epsg} to WGS84")
    st.markdown("---")
    
    # ===== DISTANCE UNIT SELECTION =====
    st.subheader("📏 Distance Unit")
    distance_unit = st.selectbox(
        "Select unit for display & ruler:",
        ["Meters (m)", "Kilometers (km)", "Feet (ft)"],
        index=0
    )
    st.caption("✨ Changes table, tooltips, AND the ruler tool.")
    
    st.markdown("---")
    
    # Load Data
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
        search_radius_m = st.number_input("📏 Search Radius (meters)", min_value=0.0, value=500.0, step=50.0)
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
    nearby_df = df[df['distance'] <= search_radius_m].copy()
    nearby_df = nearby_df.sort_values('distance').reset_index(drop=True)
    
    unit_label = get_unit_label(distance_unit)
    nearby_df[f'Distance ({unit_label})'] = nearby_df['distance'].apply(lambda d: format_distance(d, distance_unit))
    
    st.markdown(f"### ✅ Results for Well **{selected_well}**")
    col1, col2, col3 = st.columns(3)
    col1.metric("Nearby Wells", len(nearby_df))
    if not nearby_df.empty:
        col2.metric("Closest Well", nearby_df.iloc[0]['Well'])
        closest_dist = format_distance(nearby_df.iloc[0]['distance'], distance_unit)
        col3.metric("Closest Distance", f"{closest_dist:.3f} {unit_label}")
    else:
        col2.metric("Closest Well", "-")
        col3.metric("Closest Distance", "-")
    
    st.markdown("#### 📋 Nearby Wells Table (Searchable & Filterable)")
    if not nearby_df.empty:
        display_cols = ['Well', 'x', 'y', f'Distance ({unit_label})']
        st.dataframe(
            nearby_df[display_cols].style.format({f'Distance ({unit_label})': '{:.3f}'}),
            use_container_width=True,
            height=300
        )
    else:
        st.warning("No wells found within radius.")
    
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
    
    st.markdown("#### 🗺️ General Map (All Wells)")
    st.caption("🖱️ Hover over wells for details. 🧭 Click the ruler icon (top-right) to measure distances. ☰ Click layers icon to change map style.")
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
    st_folium(m1, width=1200, height=500, returned_objects=[])
    
    st.markdown("#### 🔍 Zoom View (Selected + Nearby Wells Only)")
    nearby_wells = df[df['distance'] <= search_radius_m].copy()
    if selected_well not in nearby_wells['Well'].values:
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
        st_folium(m2, width=1200, height=450, returned_objects=[])
    else:
        st.info("No nearby wells to zoom in on.")
    
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        if not nearby_df.empty:
            csv = nearby_df[['Well', 'x', 'y', f'Distance ({unit_label})']].to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Results CSV", data=csv, file_name='nearest_wells.csv', mime='text/csv', use_container_width=True)
    
    with col_dl2:
        if 'm1' in locals():
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

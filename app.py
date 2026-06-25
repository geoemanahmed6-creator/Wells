import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import MeasureControl
from streamlit_folium import folium_static
from pyproj import Transformer
import tempfile
import os
import zipfile
import io
import shapefile  # pyshp
# ==================== PAGE CONFIG (FULL WIDTH & COMPACT) ====================
st.set_page_config(page_title="Nearest Wells Finder", layout="wide", initial_sidebar_state="expanded")

# ==================== CUSTOM CSS (REDUCE PADDING FOR FIT-TO-SCREEN) ====================
def apply_theme(theme):
    # تقليل الهوامش العلوية والسفلية لجعل المحتوى يغطي الشاشة
    padding_top = "0.5rem" if theme == "Dark" else "0.5rem"
    padding_bottom = "0.5rem"
    
    base_css = f"""
    <style>
        .stApp {{ background: {'#0b0e14' if theme == "Dark" else '#f8fafc'}; font-family: 'Poppins', sans-serif; }}
        .main .block-container {{
            padding-top: {padding_top};
            padding-bottom: {padding_bottom};
            max-width: 100%;
        }}
        .stSidebar {{ background: {'linear-gradient(180deg, #161b24 0%, #0b0e14 100%)' if theme == "Dark" else 'linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%)'}; border-right: 1px solid {'#2a313c' if theme == "Dark" else '#e2e8f0'}; }}
        .stSidebar .stMarkdown, .stSidebar .stText, .stSidebar .stSelectbox, .stSidebar .stNumberInput {{ color: {'#e0e4e8' if theme == "Dark" else '#1e293b'}; }}
        h1, h2, h3, h4, .stTitle, .stHeader {{ color: {'#ffffff' if theme == "Dark" else '#0f172a'} !important; font-weight: 600 !important; }}
        div[data-testid="stMetricValue"] {{ color: {'#f0b90b' if theme == "Dark" else '#2563eb'} !important; font-size: 1.8rem !important; font-weight: 700; }}
        div[data-testid="stMetricLabel"] {{ color: {'#a0aec0' if theme == "Dark" else '#475569'} !important; }}
        .stDataFrame {{ background: {'#161b24' if theme == "Dark" else '#ffffff'}; border-radius: 12px; border: 1px solid {'#2a313c' if theme == "Dark" else '#e2e8f0'}; }}
        .stDataFrame thead tr th {{ background: {'#1f2937' if theme == "Dark" else '#f1f5f9'} !important; color: {'#f0b90b' if theme == "Dark" else '#0f172a'} !important; }}
        .stDataFrame tbody tr td {{ color: {'#e2e8f0' if theme == "Dark" else '#1e293b'} !important; }}
        .stButton > button {{ background: {'linear-gradient(90deg, #f0b90b, #d69e04)' if theme == "Dark" else 'linear-gradient(90deg, #2563eb, #1d4ed8)'}; color: {'#0b0e14' if theme == "Dark" else '#ffffff'}; font-weight: 600; border: none; border-radius: 8px; padding: 0.4rem 1.2rem; box-shadow: 0 4px 15px rgba({('240, 185, 11' if theme == "Dark" else '37, 99, 235')}, 0.3); }}
        .stButton > button:hover {{ transform: scale(1.02); box-shadow: 0 6px 20px rgba({('240, 185, 11' if theme == "Dark" else '37, 99, 235')}, 0.5); }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 2px; background-color: {'#1f2937' if theme == "Dark" else '#e2e8f0'}; border-radius: 10px; padding: 4px; }}
        .stTabs [data-baseweb="tab"] {{ border-radius: 8px; padding: 4px 12px; color: {'#94a3b8' if theme == "Dark" else '#475569'}; font-size: 0.9rem; }}
        .stTabs [aria-selected="true"] {{ background-color: {'#f0b90b' if theme == "Dark" else '#2563eb'} !important; color: {'#0b0e14' if theme == "Dark" else '#ffffff'} !important; font-weight: 600; }}
        .stCaption {{ font-size: 0.7rem; }}
        /* تقليل المسافات بين العناصر */
        .element-container {{ margin-bottom: 0.2rem !important; }}
        .stMarkdown {{ margin-bottom: 0.2rem !important; }}
    </style>
    """
    st.markdown(base_css, unsafe_allow_html=True)

# ==================== GOOGLE FONTS ====================
st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# ==================== CRS FUNCTIONS ====================
@st.cache_resource
def get_transformer(source_epsg):
    try:
        return Transformer.from_crs(f"epsg:{source_epsg}", "epsg:4326", always_xy=True)
    except Exception as e:
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
def clean_numeric_column(series):
    series = series.astype(str)
    series = series.str.replace(r'[^\d\.\-]', '', regex=True)
    return pd.to_numeric(series, errors='coerce')

def load_wells_file(uploaded_file):
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(uploaded_file, engine='openpyxl')
            else:
                df = pd.read_csv(uploaded_file)
            return df
        except Exception as e:
            st.error(f"Error reading file: {e}")
            return None
    return None

# ==================== LOAD POLYGON FROM SHAPEFILE (ZIP) ====================
def load_polygon_from_zip(uploaded_zip):
    if uploaded_zip is not None:
        try:
            # قراءة الملف المضغوط
            with zipfile.ZipFile(io.BytesIO(uploaded_zip.read())) as z:
                # البحث عن ملف .shp داخل الـ Zip
                shp_files = [f for f in z.namelist() if f.endswith('.shp')]
                if not shp_files:
                    st.error("No .shp file found in the ZIP archive.")
                    return None
                shp_file = shp_files[0]
                
                # استخراج محتوى .shp إلى ذاكرة مؤقتة
                shp_data = z.read(shp_file)
                
                # البحث عن ملفات .shx و .dbf المصاحبة
                shx_name = shp_file.replace('.shp', '.shx')
                dbf_name = shp_file.replace('.shp', '.dbf')
                
                shx_data = z.read(shx_name) if shx_name in z.namelist() else None
                dbf_data = z.read(dbf_name) if dbf_name in z.namelist() else None
                
                # قراءة الـ Shapefile باستخدام pyshp من الذاكرة
                # pyshp يتوقع مسار ملف أو BytesIO
                from io import BytesIO
                shp_io = BytesIO(shp_data)
                shx_io = BytesIO(shx_data) if shx_data else None
                dbf_io = BytesIO(dbf_data) if dbf_data else None
                
                # فتح القارئ
                if shx_io and dbf_io:
                    reader = shapefile.Reader(shp=shp_io, shx=shx_io, dbf=dbf_io)
                else:
                    reader = shapefile.Reader(shp=shp_io)
                
                shapes = reader.shapes()
                if not shapes:
                    st.error("No shapes found in the shapefile.")
                    return None
                
                # نأخذ أول مضلع (يفترض أن المضلع واحد)
                # استخراج النقاط (x, y)
                points = shapes[0].points
                
                # تحويل إلى قائمة [x, y] ليتوافق مع الكود السابق
                polygon_coords = [[p[0], p[1]] for p in points]
                return polygon_coords
                
        except Exception as e:
            st.error(f"Error reading shapefile: {e}")
            return None
    return None

# ==================== BUILD MAP (WITH CUSTOM TOOLTIP) ====================
def build_map(center_lat, center_lon, zoom_start, df, selected_well, search_radius, polygon_points, 
              transformer_global, unit, zoom_mode=False, 
              well_col='Well', x_col='x', y_col='y', epsg_col=None, hover_cols=None):
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles=None, control_scale=True)
    
    # Tile Layers
    folium.TileLayer('OpenStreetMap', name='🗺️ Street Map', show=True).add_to(m)
    folium.TileLayer('OpenTopoMap', name='🏔️ Topographic', show=False).add_to(m)
    folium.TileLayer('CartoDB positron', name='🌐 Light Simple', show=False).add_to(m)
    folium.TileLayer('CartoDB dark_matter', name='🌑 Dark Simple', show=False).add_to(m)
    
    # Measure Tool
    primary, secondary = get_measure_units(unit)
    MeasureControl(position='topright', primary_length_unit=primary, secondary_length_unit=secondary,
                   active_color='red', completed_color='#ff0000', toggle_display=True).add_to(m)
    
    # Polygon
    poly_latlng = []
    if polygon_points:
        try:
            for x, y in polygon_points:
                lat, lon = utm_to_latlng(transformer_global, x, y)
                if lat is not None and lon is not None:
                    poly_latlng.append([lat, lon])
            if poly_latlng:
                folium.Polygon(locations=poly_latlng, color="green", weight=3, fill=True, 
                               fill_color="green", fill_opacity=0.15, popup="Boundary").add_to(m)
        except:
            pass
    
    # Search Radius
    folium.Circle(location=[center_lat, center_lon], radius=search_radius, color='red', 
                  weight=2, fill=False, popup=f"Radius: {search_radius} {get_unit_label(unit)}").add_to(m)
    
    # ----- Wells Loop (With Customizable Tooltip) -----
    # إذا لم يتم تحديد hover_cols، نعرض فقط اسم البئر والمسافة
    if hover_cols is None:
        hover_cols = []
    
    for idx, row in df.iterrows():
        well_name = row[well_col]
        
        if epsg_col and epsg_col in df.columns and pd.notna(row[epsg_col]):
            epsg_code = int(row[epsg_col])
            transformer = get_transformer(epsg_code)
            if transformer is None:
                continue
        else:
            transformer = transformer_global
        
        lat, lon = utm_to_latlng(transformer, row[x_col], row[y_col])
        if lat is None or lon is None:
            continue
        
        dist_m = row.get('distance', 0)
        dist_formatted = format_distance(dist_m, unit)
        dist_label = get_unit_label(unit)
        
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
        
        # بناء التلميح (Tooltip) بناءً على الأعمدة المختارة من قبل المستخدم
        tooltip_text = f"<b>Well:</b> {well_name}<br>"
        
        # عرض الأعمدة المختارة (مع استبعاد الأعمدة الأساسية التي قد تم اختيارها)
        for col in hover_cols:
            if col in row and col not in [well_col, x_col, y_col, 'distance', 'lat', 'lon']:
                tooltip_text += f"<b>{col}:</b> {row[col]}<br>"
        
        tooltip_text += f"<b>Distance:</b> {dist_formatted:.3f} {dist_label}"
        
        tooltip = folium.Tooltip(tooltip_text, sticky=True)
        
        folium.Marker(
            location=[lat, lon],
            popup=f"<b>{well_name}</b>",
            tooltip=tooltip,
            icon=folium.Icon(color=color, icon=icon_type, prefix='glyphicon')
        ).add_to(m)
    
    # Legend
    bg_color = '#161b24' if st.session_state.get('theme', 'Light') == 'Dark' else '#ffffff'
    text_color = '#e2e8f0' if st.session_state.get('theme', 'Light') == 'Dark' else '#1e293b'
    border_color = '#2a313c' if st.session_state.get('theme', 'Light') == 'Dark' else '#e2e8f0'
    
    legend_html = f'''
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000; 
                background: {bg_color}; padding: 6px 12px; 
                border-radius: 8px; border: 1px solid {border_color}; 
                font-size: 11px; font-family: 'Poppins', Arial; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                color: {text_color}; line-height: 1.6; backdrop-filter: blur(4px);">
        <b style="font-size:12px;">📍 Legend</b><br>
        <span style="color: #ef4444;">●</span> Selected<br>
        <span style="color: #3b82f6;">●</span> Nearby<br>
        <span style="color: #94a3b8;">●</span> Other<br>
        <span style="color: #22c55e; border: 1px solid #22c55e; padding: 0px 8px;">▬</span> Boundary
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    folium.LayerControl(position='topright', collapsed=False).add_to(m)
    return m

# ==================== SESSION STATE INIT ====================
if 'df' not in st.session_state:
    st.session_state.df = None
if 'polygon_points' not in st.session_state:
    st.session_state.polygon_points = None
if 'search_data' not in st.session_state:
    st.session_state.search_data = None
if 'search_active' not in st.session_state:
    st.session_state.search_active = False

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    
    # Theme
    theme_choice = st.radio("🎨 Theme", ["Light", "Dark"], index=0)
    st.session_state['theme'] = theme_choice
    apply_theme(theme_choice)
    
    st.markdown("---")
    
    # File Uploads
    uploaded_file = st.file_uploader("📂 Upload Wells (Excel/CSV)", type=['xlsx', 'xls', 'csv'])
    uploaded_poly = st.file_uploader("📂 Upload Polygon (ZIP - Shapefile)", type=['zip'])
    
    if uploaded_file is not None:
        df = load_wells_file(uploaded_file)
        if df is not None:
            st.session_state.df = df
            st.session_state.search_active = False
    elif st.session_state.df is None:
        sample = pd.DataFrame({
            'Well': ['WD-013', 'WD-068', 'WD-061'],
            'x': [8863112.854, 8863308.970, 8863274.206],
            'y': [6657796.548, 6657795.664, 6657957.022],
            'Production_Rate': [120, 85, 95],
            'Pressure': [3200, 3100, 3050]
        })
        st.session_state.df = sample
        st.info("💡 Using sample data.")
    
    if uploaded_poly is not None:
        st.session_state.polygon_points = load_polygon_from_zip(uploaded_poly)
        if st.session_state.polygon_points:
            st.success("✅ Polygon loaded successfully!")
    
    df = st.session_state.df
    polygon_points = st.session_state.polygon_points
    
    if df is not None and not df.empty:
        st.markdown("---")
        st.subheader("📋 Column Mapping")
        
        well_col = st.selectbox("Well Name", df.columns, index=list(df.columns).index('Well') if 'Well' in df.columns else 0)
        x_col = st.selectbox("X Coordinate", df.columns, index=list(df.columns).index('x') if 'x' in df.columns else 0)
        y_col = st.selectbox("Y Coordinate", df.columns, index=list(df.columns).index('y') if 'y' in df.columns else 1)
        
        epsg_col = None
        if 'EPSG' in df.columns or 'epsg' in df.columns:
            epsg_options = [c for c in df.columns if c.lower() == 'epsg']
            epsg_col = epsg_options[0]
            st.success(f"✅ Found EPSG column '{epsg_col}'")
        else:
            st.info("ℹ️ No EPSG column found.")
        
        st.markdown("---")
        st.subheader("🔧 Coordinate Correction")
        y_shift = st.number_input("➕ Y Offset (m)", value=0.0, step=100000.0, format="%f")
        if y_shift != 0:
            st.success(f"✅ Y increased by {y_shift:,.0f} m")
            df[y_col] = df[y_col] + y_shift
            st.session_state.df = df
            st.session_state.search_active = False
        
        st.markdown("---")
        crs_options = {
            "WGS 84 / UTM Zone 36N (32636)": 32636,
            "WGS 84 / UTM Zone 37N (32637)": 32637,
            "Egypt 1907 / Red Belt (22992)": 22992,
            "Egypt 1907 / Blue Belt (22991)": 22991,
            "Egypt 1907 / Purple Belt (22993)": 22993,
            "Egypt 1907 / Extended Purple (22994)": 22994,
            "WGS 84 Geographic (4326)": 4326,
            "Custom": "custom"
        }
        selected_crs_label = st.selectbox("🌍 Source CRS", list(crs_options.keys()), index=0)
        if crs_options[selected_crs_label] == "custom":
            custom_epsg = st.number_input("EPSG Code", value=32636, step=1)
            source_epsg = int(custom_epsg)
        else:
            source_epsg = crs_options[selected_crs_label]
        
        st.markdown("---")
        st.subheader("📏 Distance Unit")
        distance_unit = st.selectbox("Unit", ["Meters (m)", "Kilometers (km)", "Feet (ft)"], index=0)
        
        st.markdown("---")
        
        # ===== NEW: TOOLTIP CUSTOMIZATION =====
        st.subheader("🖱️ Tooltip Settings")
        st.caption("Select additional fields to show on hover (Well & Distance are always shown).")
        
        # الأعمدة المتاحة للعرض في التلميح (نستثني الأعمدة الأساسية)
        all_cols = df.columns.tolist()
        exclude_cols = [well_col, x_col, y_col]
        available_cols = [c for c in all_cols if c not in exclude_cols]
        
        default_cols = []
        if 'Production_Rate' in available_cols:
            default_cols.append('Production_Rate')
        if 'Pressure' in available_cols:
            default_cols.append('Pressure')
        
        hover_cols = st.multiselect(
            "Select fields to show in tooltip:",
            available_cols,
            default=default_cols
        )
        st.markdown("---")
        
        well_list = df[well_col].tolist()
        selected_well = st.selectbox("🟢 Select a Well", well_list, index=0)
        search_radius_m = st.number_input("📏 Search Radius (m)", min_value=0.0, value=500.0, step=50.0)
        search_clicked = st.button("🔍 Find Nearby Wells", use_container_width=True, type="primary")
        
        if search_clicked:
            st.session_state.search_active = False
    else:
        st.warning("Please upload a valid file.")
        st.stop()

# ==================== MAIN CONTENT (TABS) ====================
if df is not None and not df.empty:
    tab1, tab2 = st.tabs(["🗺️ Map & Search", "📊 Data Management"])
    
    with tab1:
        # ================================================================
        # 1. NEW SEARCH
        # ================================================================
        if search_clicked:
            df_temp = df.copy()
            
            df_temp[x_col] = clean_numeric_column(df_temp[x_col])
            df_temp[y_col] = clean_numeric_column(df_temp[y_col])
            df_temp = df_temp.dropna(subset=[x_col, y_col])
            
            if not df_temp.empty:
                selected_row = df_temp[df_temp[well_col] == selected_well]
                if not selected_row.empty:
                    sel_x = selected_row[x_col].values[0]
                    sel_y = selected_row[y_col].values[0]
                    
                    df_temp['distance'] = np.sqrt((df_temp[x_col] - sel_x)**2 + (df_temp[y_col] - sel_y)**2)
                    nearby_df = df_temp[(df_temp['distance'] <= search_radius_m) & (df_temp[well_col] != selected_well)].copy()
                    nearby_df = nearby_df.sort_values('distance').reset_index(drop=True)
                    
                    unit_label = get_unit_label(distance_unit)
                    nearby_df[f'Distance ({unit_label})'] = nearby_df['distance'].apply(lambda d: format_distance(d, distance_unit))
                    
                    extra_cols = [c for c in df_temp.columns if c not in [well_col, x_col, y_col, 'distance']]
                    
                    transformer_global = get_transformer(source_epsg)
                    if transformer_global is not None:
                        def convert_row(row):
                            if epsg_col and epsg_col in row and pd.notna(row[epsg_col]):
                                epsg = int(row[epsg_col])
                                transformer = get_transformer(epsg)
                                if transformer is None:
                                    return pd.Series([None, None], index=['lat', 'lon'])
                            else:
                                transformer = transformer_global
                            lat, lon = utm_to_latlng(transformer, row[x_col], row[y_col])
                            return pd.Series([lat, lon], index=['lat', 'lon'])
                        
                        df_latlng = df_temp.apply(convert_row, axis=1)
                        df_temp = pd.concat([df_temp, df_latlng], axis=1)
                        df_temp = df_temp.dropna(subset=['lat', 'lon'])
                        
                        if not df_temp.empty:
                            center_lat = df_temp[df_temp[well_col] == selected_well]['lat'].values[0]
                            center_lon = df_temp[df_temp[well_col] == selected_well]['lon'].values[0]
                            
                            m1 = build_map(
                                center_lat=center_lat, center_lon=center_lon, zoom_start=12,
                                df=df_temp, selected_well=selected_well, search_radius=search_radius_m,
                                polygon_points=polygon_points, transformer_global=transformer_global,
                                unit=distance_unit, zoom_mode=False,
                                well_col=well_col, x_col=x_col, y_col=y_col, epsg_col=epsg_col,
                                hover_cols=hover_cols
                            )
                            
                            nearby_wells = df_temp[(df_temp['distance'] <= search_radius_m) & (df_temp[well_col] != selected_well)].copy()
                            nearby_wells = pd.concat([nearby_wells, df_temp[df_temp[well_col] == selected_well]])
                            m2 = None
                            if not nearby_wells.empty:
                                center_lat_zoom = nearby_wells['lat'].mean()
                                center_lon_zoom = nearby_wells['lon'].mean()
                                m2 = build_map(
                                    center_lat=center_lat_zoom, center_lon=center_lon_zoom, zoom_start=14,
                                    df=nearby_wells, selected_well=selected_well, search_radius=search_radius_m,
                                    polygon_points=polygon_points, transformer_global=transformer_global,
                                    unit=distance_unit, zoom_mode=True,
                                    well_col=well_col, x_col=x_col, y_col=y_col, epsg_col=epsg_col,
                                    hover_cols=hover_cols
                                )
                            
                            st.session_state.search_data = {
                                'df_temp': df_temp,
                                'nearby_df': nearby_df,
                                'extra_cols': extra_cols,
                                'm1': m1,
                                'm2': m2,
                                'selected_well': selected_well,
                                'distance_unit': distance_unit,
                                'unit_label': unit_label,
                                'search_radius_m': search_radius_m,
                                'well_col': well_col,
                                'x_col': x_col,
                                'y_col': y_col,
                                'hover_cols': hover_cols
                            }
                            st.session_state.search_active = True
                        else:
                            st.error("Conversion failed.")
                    else:
                        st.error("Invalid CRS.")
                else:
                    st.error("Well not found!")
            else:
                st.error("No valid coordinates.")
        
        # ================================================================
        # 2. DISPLAY RESULTS (CACHED)
        # ================================================================
        if st.session_state.search_active and st.session_state.search_data is not None:
            data = st.session_state.search_data
            df_temp = data['df_temp']
            nearby_df = data['nearby_df']
            extra_cols = data['extra_cols']
            m1 = data['m1']
            m2 = data['m2']
            selected_well = data['selected_well']
            distance_unit = data['distance_unit']
            unit_label = data['unit_label']
            search_radius_m = data['search_radius_m']
            well_col = data['well_col']
            x_col = data['x_col']
            y_col = data['y_col']
            
            # Stats
            st.markdown(f"### 🎯 Results for Well **{selected_well}**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📌 Nearby Wells", len(nearby_df))
            with col2:
                if not nearby_df.empty:
                    st.metric("🏆 Closest Well", nearby_df.iloc[0][well_col])
                else:
                    st.metric("🏆 Closest Well", "-")
            with col3:
                if not nearby_df.empty:
                    closest_dist = format_distance(nearby_df.iloc[0]['distance'], distance_unit)
                    st.metric("📏 Closest Dist", f"{closest_dist:.2f} {unit_label}")
                else:
                    st.metric("📏 Closest Dist", "-")
            
            st.markdown("---")
            
            # Table (تقليل الارتفاع قليلاً)
            st.markdown("#### 📋 Nearby Wells")
            if not nearby_df.empty:
                display_cols = [well_col, x_col, y_col, f'Distance ({unit_label})']
                display_cols.extend(extra_cols)
                st.dataframe(
                    nearby_df[display_cols].style.format({f'Distance ({unit_label})': '{:.2f}'}),
                    use_container_width=True,
                    height=250
                )
            else:
                st.warning("⚠️ No other wells found.")
            
            # Map 1 (تقليل الارتفاع لتقليل التمرير)
            st.markdown("#### 🗺️ General Map")
            st.caption("🖱️ Hover for details | 🧭 Ruler | ☰ Layers")
            folium_static(m1, width=1200, height=450)
            
            # Map 2
            st.markdown("#### 🔍 Zoom View")
            if m2 is not None:
                folium_static(m2, width=1200, height=400)
            else:
                st.info("ℹ️ No nearby wells to zoom.")
            
            # Download
            st.markdown("---")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                if not nearby_df.empty:
                    csv = nearby_df[[well_col, x_col, y_col, f'Distance ({unit_label})'] + extra_cols].to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download CSV", data=csv, file_name='nearest_wells.csv', mime='text/csv', use_container_width=True)
            with col_dl2:
                html_path = tempfile.NamedTemporaryFile(delete=False, suffix='.html').name
                m1.save(html_path)
                with open(html_path, 'r', encoding='utf-8') as f:
                    html_data = f.read()
                st.download_button("🗺️ Export HTML", data=html_data, file_name='wells_map.html', mime='text/html', use_container_width=True)
                try:
                    os.unlink(html_path)
                except:
                    pass
        else:
            if not search_clicked:
                st.info("👈 Select settings and click 'Find Nearby Wells'.")
    
    # ================================================================
    # TAB 2: DATA MANAGEMENT
    # ================================================================
    with tab2:
        st.markdown("### 📊 All Wells Data")
        if st.session_state.df is not None:
            with st.form(key="data_edit_form"):
                edited_df = st.data_editor(
                    st.session_state.df,
                    num_rows="dynamic",
                    use_container_width=True,
                    height=500,
                    column_config={
                        "Well": st.column_config.TextColumn("Well Name", required=True),
                        "x": st.column_config.NumberColumn("X", format="%.2f"),
                        "y": st.column_config.NumberColumn("Y", format="%.2f"),
                    }
                )
                submitted = st.form_submit_button("💾 Save Changes", use_container_width=True, type="primary")
            
            if submitted:
                st.session_state.df = edited_df
                st.session_state.search_active = False
                st.success(f"✅ Saved! Total: {len(edited_df)}")
                st.rerun()
            
            csv_full = st.session_state.df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Full Dataset", data=csv_full, file_name='all_wells_data.csv', mime='text/csv')
        else:
            st.warning("No data loaded.")

else:
    st.warning("Please upload a valid file.")

st.markdown("---")
st.caption("🔒 Local | 🖱️ Hover for details | 🧭 Ruler | 📦 Shapefile support")

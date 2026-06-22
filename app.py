import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import MeasureControl
from streamlit_folium import folium_static
from pyproj import Transformer
import tempfile
import os

# ==================== PAGE CONFIG ====================
st.set_page_config(page_title="Nearest Wells Finder", layout="wide", initial_sidebar_state="expanded")

# ==================== GOOGLE FONTS ====================
st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# ==================== CUSTOM CSS (PROFESSIONAL UI) ====================
def apply_theme(theme):
    if theme == "Dark":
        st.markdown("""
        <style>
            .stApp { background: #0b0e14; font-family: 'Poppins', sans-serif; }
            .stSidebar { background: linear-gradient(180deg, #161b24 0%, #0b0e14 100%); border-right: 1px solid #2a313c; }
            .stSidebar .stMarkdown, .stSidebar .stText, .stSidebar .stSelectbox, .stSidebar .stNumberInput { color: #e0e4e8; }
            h1, h2, h3, h4, .stTitle, .stHeader { color: #ffffff !important; font-weight: 600 !important; }
            div[data-testid="stMetricValue"] { color: #f0b90b !important; font-size: 2.2rem !important; font-weight: 700; }
            div[data-testid="stMetricLabel"] { color: #a0aec0 !important; }
            .stDataFrame { background: #161b24; border-radius: 12px; border: 1px solid #2a313c; }
            .stDataFrame thead tr th { background: #1f2937 !important; color: #f0b90b !important; }
            .stDataFrame tbody tr td { color: #e2e8f0 !important; }
            .stButton > button { background: linear-gradient(90deg, #f0b90b, #d69e04); color: #0b0e14; font-weight: 600; border: none; border-radius: 8px; padding: 0.6rem 1.5rem; box-shadow: 0 4px 15px rgba(240, 185, 11, 0.3); }
            .stButton > button:hover { transform: scale(1.02); box-shadow: 0 6px 20px rgba(240, 185, 11, 0.5); }
            .stTabs [data-baseweb="tab-list"] { gap: 2px; background-color: #1f2937; border-radius: 10px; padding: 4px; }
            .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 8px 16px; color: #94a3b8; }
            .stTabs [aria-selected="true"] { background-color: #f0b90b !important; color: #0b0e14 !important; font-weight: 600; }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
            .stApp { background: #f8fafc; font-family: 'Poppins', sans-serif; }
            .stSidebar { background: linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%); border-right: 1px solid #e2e8f0; }
            h1, h2, h3, h4, .stTitle, .stHeader { color: #0f172a !important; font-weight: 600 !important; }
            div[data-testid="stMetricValue"] { color: #2563eb !important; font-size: 2.2rem !important; font-weight: 700; }
            div[data-testid="stMetricLabel"] { color: #475569 !important; }
            .stDataFrame { background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; }
            .stDataFrame thead tr th { background: #f1f5f9 !important; color: #0f172a !important; }
            .stDataFrame tbody tr td { color: #1e293b !important; }
            .stButton > button { background: linear-gradient(90deg, #2563eb, #1d4ed8); color: #ffffff; font-weight: 600; border: none; border-radius: 8px; padding: 0.6rem 1.5rem; box-shadow: 0 4px 15px rgba(37, 99, 235, 0.3); }
            .stButton > button:hover { transform: scale(1.02); box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5); }
            .stTabs [data-baseweb="tab-list"] { gap: 2px; background-color: #e2e8f0; border-radius: 10px; padding: 4px; }
            .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 8px 16px; color: #475569; }
            .stTabs [aria-selected="true"] { background-color: #2563eb !important; color: #ffffff !important; font-weight: 600; }
        </style>
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

# ==================== DATA LOADING & CLEANING ====================
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

# ==================== BUILD MAP (NO HIGHLIGHT) ====================
def build_map(center_lat, center_lon, zoom_start, df, selected_well, search_radius, polygon_points, 
              transformer_global, unit, zoom_mode=False, 
              well_col='Well', x_col='x', y_col='y', epsg_col=None):
    
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
    
    # ----- Wells Loop -----
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
        
        tooltip_text = f"<b>Well:</b> {well_name}<br>"
        for col in df.columns:
            if col not in [well_col, x_col, y_col, 'distance', 'lat', 'lon']:
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
                background: {bg_color}; padding: 8px 14px; 
                border-radius: 10px; border: 1px solid {border_color}; 
                font-size: 12px; font-family: 'Poppins', Arial; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                color: {text_color}; line-height: 1.8; backdrop-filter: blur(4px);">
        <b style="font-size:13px;">📍 Legend</b><br>
        <span style="color: #ef4444;">●</span> Selected Well (Main)<br>
        <span style="color: #3b82f6;">●</span> Nearby Well (within radius)<br>
        <span style="color: #94a3b8;">●</span> Other Well (outside radius)<br>
        <span style="color: #22c55e; border: 1px solid #22c55e; padding: 0px 10px;">▬</span> Boundary Polygon
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

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    
    theme_choice = st.radio("🎨 Theme", ["Light", "Dark"], index=0)
    st.session_state['theme'] = theme_choice
    apply_theme(theme_choice)
    
    st.markdown("---")
    
    uploaded_file = st.file_uploader("📂 Upload Wells (Excel/CSV)", type=['xlsx', 'xls', 'csv'])
    uploaded_poly = st.file_uploader("📂 Upload Boundary (optional)", type=['xlsx', 'xls', 'csv'])
    
    if uploaded_file is not None:
        df = load_wells_file(uploaded_file)
        if df is not None:
            st.session_state.df = df
    elif st.session_state.df is None:
        sample = pd.DataFrame({
            'Well': ['WD-013', 'WD-068', 'WD-061'],
            'x': [8863112.854, 8863308.970, 8863274.206],
            'y': [6657796.548, 6657795.664, 6657957.022],
            'Production_Rate': [120, 85, 95],
            'Pressure': [3200, 3100, 3050]
        })
        st.session_state.df = sample
        st.info("💡 Using sample data with extra columns (Production_Rate, Pressure).")
    
    if uploaded_poly is not None:
        st.session_state.polygon_points = load_polygon_file(uploaded_poly)
    
    df = st.session_state.df
    polygon_points = st.session_state.polygon_points
    
    if df is not None and not df.empty:
        st.markdown("---")
        st.subheader("📋 Column Mapping")
        
        well_col = st.selectbox("Well Name Column", df.columns, index=list(df.columns).index('Well') if 'Well' in df.columns else 0)
        x_col = st.selectbox("X Coordinate Column", df.columns, index=list(df.columns).index('x') if 'x' in df.columns else 0)
        y_col = st.selectbox("Y Coordinate Column", df.columns, index=list(df.columns).index('y') if 'y' in df.columns else 1)
        
        epsg_col = None
        if 'EPSG' in df.columns or 'epsg' in df.columns:
            epsg_options = [c for c in df.columns if c.lower() == 'epsg']
            epsg_col = epsg_options[0]
            st.success(f"✅ Found EPSG column '{epsg_col}' - Using per-well CRS!")
        else:
            st.info("ℹ️ No 'EPSG' column found. All wells will use the global CRS selected below.")
        
        st.markdown("---")
        st.subheader("🔧 Coordinate Correction")
        y_shift = st.number_input("➕ Y Offset (meters)", value=0.0, step=100000.0, format="%f")
        if y_shift != 0:
            st.success(f"✅ Y increased by {y_shift:,.0f} m")
            df[y_col] = df[y_col] + y_shift
            st.session_state.df = df
        
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
        selected_crs_label = st.selectbox("🌍 Global Source CRS", list(crs_options.keys()), index=0)
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
        well_list = df[well_col].tolist()
        selected_well = st.selectbox("🟢 Select a Well", well_list, index=0)
        search_radius_m = st.number_input("📏 Search Radius (m)", min_value=0.0, value=500.0, step=50.0)
        search_clicked = st.button("🔍 Find Nearby Wells", use_container_width=True, type="primary")
    else:
        st.warning("Please upload a valid file.")
        st.stop()

# ==================== MAIN CONTENT (TABS) ====================
if df is not None and not df.empty:
    tab1, tab2 = st.tabs(["🗺️ Map & Search", "📊 Data Management"])
    
    with tab1:
        if search_clicked:
            df_temp = df.copy()
            
            df_temp[x_col] = clean_numeric_column(df_temp[x_col])
            df_temp[y_col] = clean_numeric_column(df_temp[y_col])
            df_temp = df_temp.dropna(subset=[x_col, y_col])
            
            if df_temp.empty:
                st.error("No valid numeric coordinates found.")
                st.stop()
            
            selected_row = df_temp[df_temp[well_col] == selected_well]
            if selected_row.empty:
                st.error("Selected well not found!")
                st.stop()
            
            sel_x = selected_row[x_col].values[0]
            sel_y = selected_row[y_col].values[0]
            
            df_temp['distance'] = np.sqrt((df_temp[x_col] - sel_x)**2 + (df_temp[y_col] - sel_y)**2)
            nearby_df = df_temp[(df_temp['distance'] <= search_radius_m) & (df_temp[well_col] != selected_well)].copy()
            nearby_df = nearby_df.sort_values('distance').reset_index(drop=True)
            
            unit_label = get_unit_label(distance_unit)
            nearby_df[f'Distance ({unit_label})'] = nearby_df['distance'].apply(lambda d: format_distance(d, distance_unit))
            
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
                    st.metric("📏 Closest Distance", f"{closest_dist:.3f} {unit_label}")
                else:
                    st.metric("📏 Closest Distance", "-")
            
            st.markdown("---")
            
            # ============================================================
            # ===== SIMPLE TABLE (NO HIGHLIGHT, NO RERUN) =====
            # ============================================================
            st.markdown("#### 📋 Nearby Wells Table")
            if not nearby_df.empty:
                display_cols = [well_col, x_col, y_col, f'Distance ({unit_label})']
                extra_cols = [c for c in df_temp.columns if c not in [well_col, x_col, y_col, 'distance']]
                display_cols.extend(extra_cols)
                
                st.dataframe(
                    nearby_df[display_cols].style.format({f'Distance ({unit_label})': '{:.3f}'}),
                    use_container_width=True,
                    height=350
                )
            else:
                st.warning("⚠️ No other wells found within the specified radius.")
            
            # ============================================================
            
            transformer_global = get_transformer(source_epsg)
            if transformer_global is None:
                st.error("Invalid global CRS.")
                st.stop()
            
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
            
            if df_temp.empty:
                st.error("Conversion failed for all wells. Check CRS or Y Offset.")
                st.stop()
            
            center_lat = df_temp[df_temp[well_col] == selected_well]['lat'].values[0]
            center_lon = df_temp[df_temp[well_col] == selected_well]['lon'].values[0]
            
            st.markdown("#### 🗺️ General Map (All Wells)")
            st.caption("🖱️ Hover wells for details. 🧭 Use ruler (top-right) to measure. ☰ Layers to change style.")
            
            m1 = build_map(
                center_lat=center_lat,
                center_lon=center_lon,
                zoom_start=12,
                df=df_temp,
                selected_well=selected_well,
                search_radius=search_radius_m,
                polygon_points=polygon_points,
                transformer_global=transformer_global,
                unit=distance_unit,
                zoom_mode=False,
                well_col=well_col,
                x_col=x_col,
                y_col=y_col,
                epsg_col=epsg_col
            )
            folium_static(m1, width=1200, height=550)
            
            st.markdown("#### 🔍 Zoom View (Selected + Nearby Wells)")
            nearby_wells = df_temp[(df_temp['distance'] <= search_radius_m) & (df_temp[well_col] != selected_well)].copy()
            nearby_wells = pd.concat([nearby_wells, df_temp[df_temp[well_col] == selected_well]])
            
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
                    transformer_global=transformer_global,
                    unit=distance_unit,
                    zoom_mode=True,
                    well_col=well_col,
                    x_col=x_col,
                    y_col=y_col,
                    epsg_col=epsg_col
                )
                folium_static(m2, width=1200, height=500)
            else:
                st.info("ℹ️ No nearby wells to zoom in on.")
            
            st.markdown("---")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                if not nearby_df.empty:
                    csv = nearby_df[[well_col, x_col, y_col, f'Distance ({unit_label})'] + extra_cols].to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Download Results CSV", data=csv, file_name='nearest_wells.csv', mime='text/csv', use_container_width=True)
            with col_dl2:
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
            st.info("👈 Select a well and settings from the sidebar, then click 'Find Nearby Wells'.")
    
    # ================================================================
    # ==================== TAB 2: DATA MANAGEMENT (WITH SAVE BUTTON) ====================
    # ================================================================
    with tab2:
        st.markdown("### 📊 All Wells Data (Editable)")
        st.caption("✏️ Edit cells freely below. Click **'💾 Save Changes'** to apply all modifications at once.")
        
        if st.session_state.df is not None:
            # استخدام st.form لمنع إعادة التشغيل أثناء التعديل
            with st.form(key="data_edit_form"):
                edited_df = st.data_editor(
                    st.session_state.df,
                    num_rows="dynamic",
                    use_container_width=True,
                    height=500,
                    column_config={
                        "Well": st.column_config.TextColumn("Well Name", required=True),
                        "x": st.column_config.NumberColumn("X Coordinate", format="%.2f"),
                        "y": st.column_config.NumberColumn("Y Coordinate", format="%.2f"),
                    }
                )
                
                # زر الحفظ داخل الفورم (لن يعيد التشغيل إلا عند الضغط عليه)
                submitted = st.form_submit_button("💾 Save Changes to Memory", use_container_width=True, type="primary")
            
            # إذا تم الضغط على زر الحفظ
            if submitted:
                st.session_state.df = edited_df
                st.success(f"✅ Data saved successfully! Total wells: {len(edited_df)}")
                st.rerun()  # نعيد التشغيل مرة واحدة لتحديث باقي التطبيق بالبيانات الجديدة
            
            # عرض العدد الحالي للبيانات (حتى لو لم يتم الحفظ بعد)
            st.info(f"📌 Current total wells in memory: {len(st.session_state.df)}")
            
            # تحميل الملف الكامل (دائماً من البيانات المحفوظة في الجلسة)
            csv_full = st.session_state.df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Full Dataset as CSV", data=csv_full, file_name='all_wells_data.csv', mime='text/csv')
        else:
            st.warning("No data loaded. Please upload a file in the sidebar.")

else:
    st.warning("Please upload a valid file in the sidebar.")

st.markdown("---")
st.caption("🔒 Local app. Data never leaves your machine. | 🖱️ Hover wells for details. | 🧭 Ruler + 4 map styles in top-right corner.")

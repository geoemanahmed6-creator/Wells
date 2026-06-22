import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
import math
import tempfile
import os

# ========== إعداد الصفحة ==========
st.set_page_config(page_title="نظام الآبار التفاعلي", layout="wide")

st.title("🗺️ نظام البحث عن الآبار القريبة مع الحدود")
st.markdown("---")

# ========== دالة تحويل UTM إلى خطوط الطول والعرض ==========
@st.cache_resource
def get_transformer(epsg_code):
    try:
        return Transformer.from_crs(f"epsg:{epsg_code}", "epsg:4326", always_xy=True)
    except Exception as e:
        st.error(f"رمز EPSG غير صحيح: {e}")
        return None

def utm_to_latlng(transformer, x, y):
    try:
        lon, lat = transformer.transform(x, y)
        return lat, lon
    except:
        return None, None

# ========== تحميل البيانات (مع بيانات تجريبية افتراضية) ==========
@st.cache_data
def load_sample_data():
    # هذه البيانات تطابق بالضبط مثال الـ Excel الذي أرفقته (WD-013 وما حولها)
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

def load_data(uploaded_file):
    if uploaded_file is not None:
        try:
            # دعم Excel و CSV
            if uploaded_file.name.endswith('.xlsx') or uploaded_file.name.endswith('.xls'):
                df = pd.read_excel(uploaded_file, engine='openpyxl')
            else:
                df = pd.read_csv(uploaded_file)
            # التأكد من وجود الأعمدة المطلوبة
            required_cols = ['Well', 'x', 'y']
            if all(col in df.columns for col in required_cols):
                return df
            else:
                st.error("الملف المرفوع يجب أن يحتوي على أعمدة: Well, x, y")
                return None
        except Exception as e:
            st.error(f"خطأ في قراءة الملف: {e}")
            return None
    return None

# ========== تحميل ملف المضلع (الحدود) ==========
@st.cache_data
def load_polygon(uploaded_poly):
    if uploaded_poly is not None:
        try:
            if uploaded_poly.name.endswith('.xlsx') or uploaded_poly.name.endswith('.xls'):
                df_poly = pd.read_excel(uploaded_poly, engine='openpyxl')
            else:
                df_poly = pd.read_csv(uploaded_poly)
            if 'x' in df_poly.columns and 'y' in df_poly.columns:
                return df_poly[['x', 'y']].values.tolist()
            else:
                st.error("ملف الحدود يجب أن يحتوي على عمودي x و y")
                return None
        except Exception as e:
            st.error(f"خطأ في قراءة ملف الحدود: {e}")
            return None
    return None

# ========== الواجهة الجانبية (Sidebar) ==========
with st.sidebar:
    st.header("⚙️ الإعدادات")
    
    # رفع ملف الآبار
    uploaded_file = st.file_uploader("📂 رفع ملف الآبار (Excel أو CSV)", type=['xlsx', 'xls', 'csv'])
    
    # رفع ملف الحدود (اختياري)
    uploaded_poly = st.file_uploader("📂 رفع ملف الحدود (Polygon) - اختياري", type=['xlsx', 'xls', 'csv'])
    
    # اختيار نظام الإسقاط (غالباً UTM Zone 36N في مصر)
    epsg_code = st.number_input("📟 رمز EPSG لنظام الإحداثيات (مثال: 32636 لمصر)", value=32636, step=1)
    
    st.markdown("---")
    
    # تحميل البيانات (إما المرفوع أو العينة)
    if uploaded_file is not None:
        df = load_data(uploaded_file)
        if df is None:
            st.stop()
    else:
        df = load_sample_data()
        st.info("💡 لم ترفعي ملفاً، جارٍ استخدام بيانات تجريبية (تشبه مثال WD-013)")
    
    # تحميل المضلع
    polygon_points = load_polygon(uploaded_poly)
    if polygon_points is None and uploaded_poly is not None:
        st.stop()

    if df is not None and not df.empty:
        # قائمة الآبار
        well_list = df['Well'].tolist()
        selected_well = st.selectbox("🟢 اختر البئر المطلوب", well_list, index=0)
        search_radius = st.number_input("📏 نصف قطر البحث (متر)", min_value=0.0, value=500.0, step=50.0)
        
        # زر البحث
        search_clicked = st.button("🔍 ابحث عن الآبار القريبة", use_container_width=True, type="primary")

# ========== المعالجة والعرض ==========
if df is not None and not df.empty and search_clicked:
    # استخراج إحداثيات البئر المختار
    selected_row = df[df['Well'] == selected_well]
    if selected_row.empty:
        st.error("البئر المحدد غير موجود!")
        st.stop()
    
    sel_x = selected_row['x'].values[0]
    sel_y = selected_row['y'].values[0]
    
    # حساب المسافات (إقليدية لأن الإحداثيات UTM بالمتر)
    df['distance'] = np.sqrt((df['x'] - sel_x)**2 + (df['y'] - sel_y)**2)
    
    # تصفية الآبار القريبة
    nearby_df = df[df['distance'] <= search_radius].copy()
    nearby_df = nearby_df.sort_values('distance').reset_index(drop=True)
    
    # ===== عرض النتائج =====
    st.markdown(f"### ✅ النتائج للبئر **{selected_well}**")
    col1, col2, col3 = st.columns(3)
    col1.metric("عدد الآبار القريبة", len(nearby_df))
    col2.metric("أقرب بئر", nearby_df.iloc[0]['Well'] if not nearby_df.empty else "-")
    col3.metric("أقرب مسافة", f"{nearby_df.iloc[0]['distance']:.2f} م" if not nearby_df.empty else "-")
    
    # الجدول
    st.markdown("#### 📋 جدول الآبار القريبة")
    if not nearby_df.empty:
        st.dataframe(
            nearby_df[['Well', 'x', 'y', 'distance']].style.format({'distance': '{:.2f}'}),
            use_container_width=True
        )
    else:
        st.warning("لا توجد آبار ضمن نصف القطر المحدد.")
    
    # ===== تحويل الإحداثيات إلى Lat/Lon لعرض الخريطة =====
    transformer = get_transformer(epsg_code)
    if transformer is None:
        st.error("فشل تحويل الإحداثيات. تأكدي من رمز EPSG.")
        st.stop()
    
    # تحويل جميع النقاط
    def convert_row(row):
        lat, lon = utm_to_latlng(transformer, row['x'], row['y'])
        return pd.Series([lat, lon], index=['lat', 'lon'])
    
    df_latlng = df.apply(convert_row, axis=1)
    df = pd.concat([df, df_latlng], axis=1)
    
    # إحداثيات البئر المختار
    center_lat = df[df['Well'] == selected_well]['lat'].values[0]
    center_lon = df[df['Well'] == selected_well]['lon'].values[0]
    
    # ===== الخريطة 1: العرض العام (كل الآبار مع الحدود) =====
    st.markdown("#### 🗺️ الخريطة العامة (جميع الآبار + الحدود)")
    m1 = folium.Map(location=[center_lat, center_lon], zoom_start=12, control_scale=True)
    
    # إضافة المضلع (الحدود) إن وجد
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
                    popup="حدود المنطقة"
                ).add_to(m1)
        except Exception as e:
            st.warning(f"تعذر رسم المضلع: {e}")
    
    # إضافة دائرة نصف القطر حول البئر المختار
    folium.Circle(
        location=[center_lat, center_lon],
        radius=search_radius,
        color='red',
        weight=2,
        fill=False,
        popup=f"نصف القطر: {search_radius} م"
    ).add_to(m1)
    
    # إضافة نقاط الآبار
    for idx, row in df.iterrows():
        if pd.isna(row['lat']) or pd.isna(row['lon']):
            continue
        well_name = row['Well']
        dist = row['distance']
        
        # تحديد اللون
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
            popup=f"{well_name}<br>المسافة: {dist:.2f} م" if dist > 0 else f"{well_name} (المختار)",
            icon=folium.Icon(color=color, icon=icon_type, prefix='glyphicon')
        ).add_to(m1)
    
    # عرض الخريطة الأولى
    st_folium(m1, width=1200, height=500, returned_objects=[])
    
    # ===== الخريطة 2: التكبير (ZooM) على الآبار القريبة فقط =====
    st.markdown("#### 🔍 خريطة التكبير (الآبار القريبة فقط)")
    # تصفية الآبار التي نريد عرضها في التكبير (المختار + القريبة)
    nearby_wells = df[df['distance'] <= search_radius].copy()
    if selected_well not in nearby_wells['Well'].values:
        # إضافة البئر المختار إن لم يكن ضمن القريبة (يحدث لو نصف القطر 0)
        nearby_wells = pd.concat([nearby_wells, df[df['Well'] == selected_well]])
    
    if not nearby_wells.empty:
        # حساب مركز الخريطة بناءً على متوسط إحداثيات الآبار القريبة
        center_lat_zoom = nearby_wells['lat'].mean()
        center_lon_zoom = nearby_wells['lon'].mean()
        
        m2 = folium.Map(location=[center_lat_zoom, center_lon_zoom], zoom_start=14, control_scale=True)
        
        # إضافة المضلع أيضاً في خريطة التكبير
        if polygon_points and poly_latlng:
            folium.Polygon(
                locations=poly_latlng,
                color="green",
                weight=2,
                fill=True,
                fill_color="green",
                fill_opacity=0.1
            ).add_to(m2)
        
        # إضافة دائرة نصف القطر
        folium.Circle(
            location=[center_lat, center_lon],
            radius=search_radius,
            color='red',
            weight=2,
            fill=False
        ).add_to(m2)
        
        # إضافة النقاط (المختار أحمر، القريبة زرقاء)
        for idx, row in nearby_wells.iterrows():
            if pd.isna(row['lat']) or pd.isna(row['lon']):
                continue
            well_name = row['Well']
            color = 'red' if well_name == selected_well else 'blue'
            icon_type = 'info-sign' if well_name == selected_well else 'ok-sign'
            
            folium.Marker(
                location=[row['lat'], row['lon']],
                popup=f"{well_name}<br>المسافة: {row['distance']:.2f} م",
                icon=folium.Icon(color=color, icon=icon_type, prefix='glyphicon')
            ).add_to(m2)
        
        st_folium(m2, width=1200, height=450, returned_objects=[])
    else:
        st.info("لا توجد آبار قريبة لتكبير الخريطة.")
    
    # ===== تنزيل النتائج =====
    if not nearby_df.empty:
        csv = nearby_df[['Well', 'x', 'y', 'distance']].to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 تحميل النتائج كـ CSV",
            data=csv,
            file_name='nearest_wells.csv',
            mime='text/csv',
        )

else:
    if not search_clicked:
        st.info("👈 اختر بئراً ونصف قطر من القائمة الجانبية، ثم اضغط زر 'ابحث عن الآبار القريبة'.")

# ========== تذييل ==========
st.markdown("---")
st.caption("🔒 التطبيق يعمل محلياً على جهازك - البيانات لا تغادر جهازك مطلقاً.")

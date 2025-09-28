import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date
import re
import warnings
import streamlit as st

warnings.filterwarnings('ignore')

# === Streamlit UI с мобильной оптимизацией ===
st.set_page_config(layout="centered", page_title="Аналитика причала 'Яхрома'")
st.title("📊 Аналитика причала 'Яхрома'")

# Мобильные стили
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Кнопка обновления данных
col1, col2 = st.columns([3, 1])
with col1:
    st.write("")  # Отступ
with col2:
    if st.button("🔄 Обновить", use_container_width=True):
        st.cache_data.clear()
        st.success("Данные обновлены!")

@st.cache_data(ttl=300)
def load_and_process_data():
    url = 'https://docs.google.com/spreadsheets/d/1rkmxMAb7B0RjM3PHknnkix_P5izTWyNIA3KTZvy9sWs/export?format=csv'
    try:
        df = pd.read_csv(url)
        st.success("✅ Данные загружены")
    except Exception as e:
        st.error(f"❌ Ошибка загрузки: {e}")
        return None

    # Нормализация названий столбцов
    def normalize_column_names(df):
        df.columns = df.columns.str.lower().str.replace('ё', 'е').str.replace('c', 'с', regex=False)
        df.columns = df.columns.str.strip()
        return df
    
    df = normalize_column_names(df)

    # Сопоставление колонок
    required_columns = ['судно', 'дата принятия на пирс', 'дата отгрузки авто',
                        'перевозчик', 'номер авто', 'тн', 'клиент', '№ сертиф.', 'брутто']
    column_mapping = {}
    
    for req_col in required_columns:
        matched = False
        for avail_col in df.columns:
            if req_col == avail_col or req_col in avail_col:
                column_mapping[req_col] = avail_col
                matched = True
                break
        if not matched:
            column_mapping[req_col] = req_col

    for standard_name, actual_name in column_mapping.items():
        if actual_name in df.columns:
            df[standard_name] = df[actual_name]
        else:
            df[standard_name] = np.nan

    # Преобразование дат
    def parse_date(date_str):
        if pd.isna(date_str) or date_str == '' or str(date_str).strip() == 'nan':
            return pd.NaT
        try:
            return datetime.strptime(str(date_str).strip(), '%d.%m.%Y')
        except:
            try:
                return pd.to_datetime(date_str)
            except:
                return pd.NaT

    df['дата_принятия_на_пирс'] = df['дата принятия на пирс'].apply(parse_date)
    df['дата_отгрузки_авто'] = df['дата отгрузки авто'].apply(parse_date)

    # Преобразование чисел
    def safe_convert_to_float(x):
        if pd.isna(x) or x == '' or str(x).strip() == 'nan':
            return np.nan
        try:
            x_str = str(x).replace(',', '.').strip()
            return float(x_str)
        except:
            return np.nan

    df['брутто'] = df['брутто'].apply(safe_convert_to_float)

    # Преобразование текста
    def safe_str_convert(x):
        if pd.isna(x) or x == '' or str(x).strip() == 'nan':
            return ''
        return str(x).strip()

    text_columns = ['судно', 'перевозчик', 'номер авто', 'тн', 'клиент', '№ сертиф.']
    for col in text_columns:
        if col in df.columns:
            df[col] = df[col].apply(safe_str_convert)

    return df

df = load_and_process_data()
if df is None:
    st.stop()

# === Подготовка данных ===
today = pd.to_datetime(date.today())

# Статусы груза
shipped = df[df['дата_отгрузки_авто'].notna()]
on_pier = df[(df['дата_принятия_на_пирс'].notna()) & (df['дата_отгрузки_авто'].isna())]
in_transit = df[(df['дата_принятия_на_пирс'].isna()) & (df['дата_отгрузки_авто'].isna())]

# === Ключевые метрики ===
st.header("📈 Ключевые показатели")

col1, col2, col3 = st.columns(3)
with col1:
    total_shipped = shipped['брутто'].sum()
    st.metric("Всего отгружено", f"{total_shipped:,.0f} т")
with col2:
    total_on_pier = on_pier['брутто'].sum()
    st.metric("На причале", f"{total_on_pier:,.0f} т")
with col3:
    total_transit = in_transit['брутто'].sum()
    st.metric("В транзите", f"{total_transit:,.0f} т")

# === 1. Объёмы по клиентам (ВСЕ клиенты) ===
st.header("👥 Объёмы по клиентам (все клиенты)")

# Собираем данные по ВСЕМ клиентам
shipped_agg = shipped.groupby('клиент')['брутто'].sum().rename('отгружено').reset_index()
on_pier_agg = on_pier.groupby('клиент')['брутто'].sum().rename('на_причале').reset_index()
in_transit_agg = in_transit.groupby('клиент')['брутто'].sum().rename('в_транзите').reset_index()

# Объединяем все данные, включая клиентов с нулевыми значениями
all_clients = df['клиент'].unique()
client_status = pd.DataFrame({'клиент': all_clients})

# Мерджим с агрегированными данными
client_status = client_status.merge(shipped_agg, on='клиент', how='left') \
    .merge(on_pier_agg, on='клиент', how='left') \
    .merge(in_transit_agg, on='клиент', how='left') \
    .fillna(0)

client_status['всего'] = client_status['отгружено'] + client_status['на_причале'] + client_status['в_транзите']
client_status = client_status.sort_values('всего', ascending=False)

# Создаем компактный график для всех клиентов
fig_clients = go.Figure()
fig_clients.add_trace(go.Bar(name='Отгружено', x=client_status['клиент'], y=client_status['отгружено'], 
                            marker_color='#FF6B6B'))
fig_clients.add_trace(go.Bar(name='На причале', x=client_status['клиент'], y=client_status['на_причале'], 
                            marker_color='#4ECDC4'))
fig_clients.add_trace(go.Bar(name='В транзите', x=client_status['клиент'], y=client_status['в_транзите'], 
                            marker_color='#45B7D1'))

fig_clients.update_layout(
    height=500,
    showlegend=True,
    barmode='stack',
    margin=dict(t=30, b=150, l=50, r=30),  # Увеличил нижний отступ для подписей
    xaxis_tickangle=-45
)
st.plotly_chart(fig_clients, use_container_width=True)

# Таблица с детальными данными по всем клиентам
with st.expander("📋 Детальная таблица по всем клиентам"):
    display_table = client_status.copy()
    display_table['отгружено'] = display_table['отгружено'].round(1)
    display_table['на_причале'] = display_table['на_причале'].round(1)
    display_table['в_транзите'] = display_table['в_транзите'].round(1)
    display_table['всего'] = display_table['всего'].round(1)
    
    st.dataframe(
        display_table,
        column_config={
            "клиент": "Клиент",
            "отгружено": st.column_config.NumberColumn("Отгружено (т)", format="%.1f т"),
            "на_причале": st.column_config.NumberColumn("На причале (т)", format="%.1f т"),
            "в_транзите": st.column_config.NumberColumn("В транзите (т)", format="%.1f т"),
            "всего": st.column_config.NumberColumn("Всего (т)", format="%.1f т"),
        },
        use_container_width=True
    )

# === 2. Отгрузка за сегодня ===
st.header("📅 Сегодняшние отгрузки")

shipped_today = shipped[shipped['дата_отгрузки_авто'].dt.date == today.date()]
shipped_today_by_client = shipped_today.groupby('клиент')['брутто'].sum().reset_index()
shipped_today_by_client = shipped_today_by_client.sort_values('брутто', ascending=False)

if len(shipped_today_by_client) > 0:
    fig_today = px.bar(shipped_today_by_client, x='клиент', y='брутто', 
                      title=f"Отгрузки за {today.strftime('%d.%m.%Y')}",
                      color='брутто', color_continuous_scale='Viridis')
    fig_today.update_layout(height=400, margin=dict(t=40, b=100, l=50, r=30),
                           xaxis_tickangle=-45)
    st.plotly_chart(fig_today, use_container_width=True)
    
    # Показать общую сумму отгрузок за сегодня
    total_today = shipped_today_by_client['брутто'].sum()
    st.info(f"Всего отгружено сегодня: **{total_today:,.1f} т**")
else:
    st.info("Сегодня отгрузок не было")

# === 3. Помесячная статистика ===
st.header("📆 Помесячная динамика")

arrival_data = df[df['дата_принятия_на_пирс'].notna()].copy()
arrival_data['год_месяц'] = arrival_data['дата_принятия_на_пирс'].dt.to_period('M')
monthly_arrivals = arrival_data.groupby('год_месяц').agg({
    'брутто': 'sum',
    '№ сертиф.': 'count'
}).reset_index()
monthly_arrivals.columns = ['месяц', 'принято_тонн', 'принято_мест']
monthly_arrivals['месяц'] = monthly_arrivals['месяц'].astype(str)

shipment_data = df[df['дата_отгрузки_авто'].notna()].copy()
shipment_data['год_месяц'] = shipment_data['дата_отгрузки_авто'].dt.to_period('M')
monthly_shipments = shipment_data.groupby('год_месяц').agg({
    'брутто': 'sum',
    'клиент': 'nunique'
}).reset_index()
monthly_shipments.columns = ['месяц', 'отгружено_тонн', 'уникальных_клиентов']
monthly_shipments['месяц'] = monthly_shipments['месяц'].astype(str)

monthly_stats = pd.merge(monthly_arrivals, monthly_shipments, on='месяц', how='outer').fillna(0)

if len(monthly_stats) > 0:
    # График принято vs отгружено
    fig_monthly = go.Figure()
    fig_monthly.add_trace(go.Bar(name='Принято', x=monthly_stats['месяц'], y=monthly_stats['принято_тонн'],
                                marker_color='#4ECDC4'))
    fig_monthly.add_trace(go.Bar(name='Отгружено', x=monthly_stats['месяц'], y=monthly_stats['отгружено_тонн'],
                                marker_color='#FF6B6B'))
    
    fig_monthly.update_layout(
        height=400, 
        margin=dict(t=40, b=80, l=50, r=30),
        xaxis_tickangle=-45,
        barmode='group'
    )
    st.plotly_chart(fig_monthly, use_container_width=True)
    
    # График уникальных клиентов по месяцам
    fig_clients_monthly = px.line(monthly_stats, x='месяц', y='уникальных_клиентов',
                                 title='Количество уникальных клиентов по месяцам',
                                 markers=True)
    fig_clients_monthly.update_layout(height=300, margin=dict(t=40, b=50, l=50, r=30))
    st.plotly_chart(fig_clients_monthly, use_container_width=True)

# === 4. Топ клиентов по общему тоннажу ===
st.header("🏆 Топ клиентов по общему тоннажу")

client_analysis = shipment_data.groupby('клиент').agg({
    'брутто': 'sum',
    '№ сертиф.': 'count'
}).reset_index()
client_analysis.columns = ['клиент', 'общий_вес', 'количество_мест']
client_analysis = client_analysis.sort_values('общий_вес', ascending=False)

# Показываем топ-15 клиентов
top_clients = client_analysis.head(15)

fig_top = px.bar(top_clients, x='общий_вес', y='клиент', orientation='h',
                title="Топ-15 клиентов по общему тоннажу",
                color='общий_вес', color_continuous_scale='Blues')
fig_top.update_layout(height=500, margin=dict(t=40, b=20, l=150, r=20))
st.plotly_chart(fig_top, use_container_width=True)

# === 5. Анализ судов ===
st.header("🚢 Анализ судов")

def analyze_circular_voyages(vessel_name):
    if pd.isna(vessel_name) or vessel_name == '':
        return vessel_name, 0
    vessel_str = str(vessel_name).strip()
    pattern = r'^(.*?)\s*\((\d+)\)\s*$'
    match = re.search(pattern, vessel_str)
    if match:
        base_name = match.group(1).strip()
        voyage_number = int(match.group(2))
        return base_name, voyage_number
    else:
        return vessel_str, 0

arrival_data = df[df['дата_принятия_на_пирс'].notna()].copy()
arrival_data[['базовое_название', 'номер_кругорейса']] = arrival_data['судно'].apply(
    lambda x: pd.Series(analyze_circular_voyages(x))
)

vessel_stats = arrival_data.groupby('базовое_название').agg({
    'дата_принятия_на_пирс': 'nunique',
    'номер_кругорейса': 'max',
    'брутто': 'sum'
}).reset_index()
vessel_stats.columns = ['судно', 'количество_заходов', 'максимальный_кругорейс', 'общий_тоннаж']
vessel_stats = vessel_stats.sort_values('общий_тоннаж', ascending=False).head(10)

if len(vessel_stats) > 0:
    fig_vessels = px.bar(vessel_stats, x='общий_тоннаж', y='судно', orientation='h',
                        title="Топ-10 судов по тоннажу",
                        color='количество_заходов', color_continuous_scale='Greens')
    fig_vessels.update_layout(height=400, margin=dict(t=40, b=20, l=150, r=20))
    st.plotly_chart(fig_vessels, use_container_width=True)

# === Информация ===
with st.expander("📖 Пояснение показателей"):
    st.markdown("""
    ### 📌 Пояснение показателей:
    
    - **Отгружено** — груз, который уже был отгружен с причала
    - **На причале** — принятый груз, который еще не отгружен  
    - **В транзите** — груз в пути к причалу
    - **Все клиенты** — включая тех, у кого малый тоннаж или нулевые показатели
    
    ### 📊 Метрики:
    - **Тоннаж** измеряется в тоннах (т)
    - **Динамика** показывает изменения по месяцам
    - **Уникальные клиенты** — количество разных клиентов в месяце
    """)

# Статус загрузки
st.success(f"✅ Данные актуальны на {datetime.now().strftime('%H:%M %d.%m.%Y')}")
st.info(f"📊 Всего клиентов в системе: **{len(client_status)}**")

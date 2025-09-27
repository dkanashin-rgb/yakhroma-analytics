import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from datetime import datetime, date
import re
import warnings
import streamlit as st

warnings.filterwarnings('ignore')

# === Streamlit UI ===
st.set_page_config(layout="wide", page_title="Аналитика причала 'Яхрома'")
st.title("ИНТЕРАКТИВНАЯ ПАНЕЛЬ АНАЛИТИКИ ПРИЧАЛА 'ЯХРОМА'")

# Кнопка обновления данных
if st.button("🔄 Обновить данные"):
    st.cache_data.clear()
    st.success("Данные будут перезагружены при следующем взаимодействии.")

@st.cache_data(ttl=300)  # кэш на 5 минут
def load_and_process_data():
    url = 'https://docs.google.com/spreadsheets/d/1rkmxMAb7B0RjM3PHknnkix_P5izTWyNIA3KTZvy9sWs/export?format=csv'
    try:
        df = pd.read_csv(url)
    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
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

# Объёмы по клиентам (всё время)
shipped_agg = shipped.groupby('клиент')['брутто'].sum().rename('отгружено').reset_index()
on_pier_agg = on_pier.groupby('клиент')['брутто'].sum().rename('на_причале').reset_index()
in_transit_agg = in_transit.groupby('клиент')['брутто'].sum().rename('в_транзите').reset_index()

client_status = shipped_agg.merge(on_pier_agg, on='клиент', how='outer') \
    .merge(in_transit_agg, on='клиент', how='outer') \
    .fillna(0)
client_status['всего'] = client_status['отгружено'] + client_status['на_причале'] + client_status['в_транзите']
client_status = client_status.sort_values('всего', ascending=False).head(15)

# Отгрузка за сегодня
shipped_today = shipped[shipped['дата_отгрузки_авто'].dt.date == today.date()]
shipped_today_by_client = shipped_today.groupby('клиент')['брутто'].sum().reset_index()
shipped_today_by_client = shipped_today_by_client.sort_values('брутто', ascending=False).head(15)

# Остальная аналитика (как в оригинале)
shipment_data = df[df['дата_отгрузки_авто'].notna()].copy()
shipment_data['уникальная_отгрузка'] = (
    shipment_data['дата_отгрузки_авто'].dt.strftime('%Y-%m-%d') + '_' +
    shipment_data['перевозчик'] + '_' +
    shipment_data['номер авто'] + '_' +
    shipment_data['тн']
)

client_analysis_all_time = shipment_data.groupby('клиент').agg({
    'уникальная_отгрузка': 'nunique',
    'брутто': 'sum',
    '№ сертиф.': 'count'
}).reset_index()
client_analysis_all_time.columns = ['клиент', 'количество_рейсов', 'общий_вес', 'количество_мест']
client_analysis_all_time['средний_тоннаж_за_рейс'] = client_analysis_all_time['общий_вес'] / client_analysis_all_time['количество_рейсов']
client_analysis_all_time = client_analysis_all_time.sort_values('средний_тоннаж_за_рейс', ascending=False)

# Помесячная статистика
arrival_data = df[df['дата_принятия_на_пирс'].notna()].copy()
arrival_data['год_месяц'] = arrival_data['дата_принятия_на_пирс'].dt.to_period('M')
monthly_arrivals = arrival_data.groupby('год_месяц').agg({
    'судно': 'nunique',
    'дата_принятия_на_пирс': 'nunique',
    'брутто': 'sum',
    '№ сертиф.': 'count'
}).reset_index()
monthly_arrivals.columns = ['месяц', 'количество_судов', 'дней_с_приходами', 'принято_тонн', 'принято_мест']
monthly_arrivals['месяц'] = monthly_arrivals['месяц'].astype(str)

shipment_data['год_месяц'] = shipment_data['дата_отгрузки_авто'].dt.to_period('M')
monthly_shipments = shipment_data.groupby('год_месяц').agg({
    'уникальная_отгрузка': 'nunique',
    'брутто': 'sum',
    'клиент': 'nunique',
    '№ сертиф.': 'count'
}).reset_index()
monthly_shipments.columns = ['месяц', 'количество_рейсов', 'отгружено_тонн', 'уникальных_клиентов', 'отгружено_мест']
monthly_shipments['месяц'] = monthly_shipments['месяц'].astype(str)

monthly_stats = pd.merge(monthly_arrivals, monthly_shipments, on='месяц', how='outer').fillna(0)
monthly_stats['средний_тоннаж_за_рейс'] = monthly_stats['отгружено_тонн'] / monthly_stats['количество_рейсов']
monthly_stats['эффективность_использования'] = np.where(
    monthly_stats['принято_тонн'] > 0,
    monthly_stats['отгружено_тонн'] / monthly_stats['принято_тонн'] * 100,
    0
)

# Анализ судов
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

arrival_data[['базовое_название', 'номер_кругорейса']] = arrival_data['судно'].apply(
    lambda x: pd.Series(analyze_circular_voyages(x))
)
vessel_visit_stats = arrival_data.groupby('базовое_название').agg({
    'дата_принятия_на_пирс': 'nunique',
    'номер_кругорейса': 'max',
    'брутто': 'sum',
    'судно': 'first'
}).reset_index()
vessel_visit_stats.columns = ['базовое_название', 'количество_заходов', 'максимальный_кругорейс', 'общий_тоннаж', 'оригинальное_название']
vessels_without_circular = vessel_visit_stats[
    (vessel_visit_stats['количество_заходов'] == 1) &
    (vessel_visit_stats['максимальный_кругорейс'] == 0)
]

# === Построение основной панели ===
fig = make_subplots(
    rows=4, cols=3,
    subplot_titles=(
        'Объёмы по клиентам: отгружено, на причале, в транзите',
        'Тоннаж отгруженный сегодня по клиентам (брутто)',
        'Помесячная динамика: принято vs отгружено',
        'Топ-15 клиентов по среднему тоннажу за рейс',
        'Количество рейсов по месяцам',
        'Эффективность использования по месяцам',
        'Распределение клиентов по тоннажу',
        'Топ-10 судов без кругорейсов',
        'Сравнение месяцев (нормализовано)',
        #'Матрица корреляции показателей',
        '', ''
    ),
    specs=[
        [{"type": "bar"}, {"type": "bar"}, {"type": "bar"}],
        [{"type": "bar"}, {"type": "bar"}, {"type": "bar"}],
        [{"type": "histogram"}, {"type": "bar"}, {"type": "bar"}],
        [{"type": "heatmap", "colspan": 3}, None, None]
    ],
    vertical_spacing=0.06,
    horizontal_spacing=0.04
)

# 1. Объёмы по клиентам (отгружено, на причале, в транзите)
if len(client_status) > 0:
    fig.add_trace(go.Bar(x=client_status['клиент'], y=client_status['отгружено'], name='Отгружено', marker_color='lightcoral'), row=1, col=1)
    fig.add_trace(go.Bar(x=client_status['клиент'], y=client_status['на_причале'], name='На причале', marker_color='lightgreen'), row=1, col=1)
    fig.add_trace(go.Bar(x=client_status['клиент'], y=client_status['в_транзите'], name='В транзите', marker_color='lightblue'), row=1, col=1)

# 2. Отгрузка за сегодня
if len(shipped_today_by_client) > 0:
    fig.add_trace(go.Bar(
        x=shipped_today_by_client['клиент'],
        y=shipped_today_by_client['брутто'],
        name='Сегодня отгружено',
        marker_color='gold',
        hovertemplate='<b>%{x}</b><br>Тоннаж: %{y:,.1f} т<extra></extra>'
    ), row=1, col=2)
else:
    fig.add_trace(go.Bar(x=["Нет данных"], y=[0], name='Сегодня отгружено', marker_color='gray'), row=1, col=2)

# 3. Помесячная динамика
if len(monthly_stats) > 0:
    fig.add_trace(go.Bar(x=monthly_stats['месяц'], y=monthly_stats['принято_тонн'], name='Принято', marker_color='lightgreen'), row=1, col=3)
    fig.add_trace(go.Bar(x=monthly_stats['месяц'], y=monthly_stats['отгружено_тонн'], name='Отгружено', marker_color='lightcoral'), row=1, col=3)

# 4. Топ-15 клиентов по среднему тоннажу за рейс
if len(client_analysis_all_time) > 0:
    top_clients = client_analysis_all_time.head(15)
    fig.add_trace(go.Bar(
        y=top_clients['клиент'],
        x=top_clients['средний_тоннаж_за_рейс'],
        orientation='h',
        marker_color='lightblue',
        name='Средний тоннаж/рейс',
        hovertemplate='<b>%{y}</b><br>Средний тоннаж: %{x:.1f} т/рейс<br>Рейсов: %{customdata}<extra></extra>',
        customdata=top_clients['количество_рейсов']
    ), row=2, col=1)

# 5. Количество рейсов по месяцам
if len(monthly_stats) > 0:
    fig.add_trace(go.Bar(x=monthly_stats['месяц'], y=monthly_stats['количество_рейсов'], name='Рейсы', marker_color='orange'), row=2, col=2)

# 6. Эффективность
if len(monthly_stats) > 0:
    colors = ['green' if e >= 90 else 'orange' if e >= 70 else 'red' for e in monthly_stats['эффективность_использования']]
    fig.add_trace(go.Bar(
        x=monthly_stats['месяц'],
        y=monthly_stats['эффективность_использования'],
        marker_color=colors,
        name='Эффективность',
        hovertemplate='<b>%{x}</b><br>Эффективность: %{y:.1f}%<extra></extra>'
    ), row=2, col=3)

# 7. Распределение клиентов
if len(client_analysis_all_time) > 0:
    fig.add_trace(go.Histogram(x=client_analysis_all_time['средний_тоннаж_за_рейс'], nbinsx=15, name='Распределение', marker_color='lightgreen'), row=3, col=1)

# 8. Суда без кругорейсов
if len(vessels_without_circular) > 0:
    top_vessels = vessels_without_circular.nlargest(10, 'общий_тоннаж')
    fig.add_trace(go.Bar(
        y=top_vessels['оригинальное_название'],
        x=top_vessels['общий_тоннаж'],
        orientation='h',
        marker_color='lightcoral',
        name='Судна без кругорейсов'
    ), row=3, col=2)

# 9. Нормализованное сравнение
if len(monthly_stats) > 0:
    metrics = ['принято_тонн', 'отгружено_тонн', 'количество_рейсов', 'количество_судов']
    names = ['Принято', 'Отгружено', 'Рейсы', 'Судна']
    colors = ['lightgreen', 'lightcoral', 'orange', 'lightblue']
    for m, n, c in zip(metrics, names, colors):
        norm = monthly_stats[m] / monthly_stats[m].max() if monthly_stats[m].max() > 0 else 0
        fig.add_trace(go.Bar(x=monthly_stats['месяц'], y=norm, name=n, marker_color=c), row=3, col=3)

# 10. Матрица корреляции
#if len(monthly_stats) > 1:
#    corr_data = monthly_stats[['принято_тонн', 'отгружено_тонн', 'количество_рейсов', 'количество_судов', 'средний_тоннаж_за_рейс']]
#    corr_matrix = corr_data.corr()
#    fig.add_trace(go.Heatmap(
#        z=corr_matrix.values,
#        x=['Принято', 'Отгружено', 'Рейсы', 'Судна', 'Тоннаж/рейс'],
#        y=['Принято', 'Отгружено', 'Рейсы', 'Судна', 'Тоннаж/рейс'],
#        colorscale='RdBu', zmin=-1, zmax=1,
#        hovertemplate='<b>%{y} vs %{x}</b><br>Корреляция: %{z:.3f}<extra></extra>',
#        colorbar=dict(title="Корреляция")
#   ), row=4, col=1)

# Настройка макета
fig.update_layout(
    height=1600,
    showlegend=True,
    barmode='stack',
    template='plotly_white',
    margin=dict(t=80, b=50, l=50, r=50)
)

# Отображение
st.plotly_chart(fig, use_container_width=True)

# Пояснения
st.markdown("""
---
### 📌 Пояснение показателей:
- **На причале** — принято, но не отгружено  
- **В транзите** — груз в пути к причалу  
- **Сегодня** — отгрузка с датой, равной текущей дате на сервере
""")

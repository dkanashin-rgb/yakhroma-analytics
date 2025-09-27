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

# === 1. Объёмы по клиентам ===
st.header("👥 Объёмы по клиентам")

shipped_agg = shipped.groupby('клиент')['брутто'].sum().rename('отгружено').reset_index()
on_pier_agg = on_pier.groupby('клиент')['брутто'].sum().rename('на_причале').reset_index()
in_transit_agg = in_transit.groupby('клиент')['брутто'].sum().rename('в_транзите').reset_index()

client_status = shipped_agg.merge(on_pier_agg, on='клиент', how='outer') \
    .merge(in_transit_agg, on='клиент', how='outer') \
    .fillna(0)
client_status['всего'] = client_status['отгружено'] + client_status['на_причале'] + client_status['в_транзите']
client_status = client_status.sort_values('всего', ascending=False).head(10)

# Создаем компактный график
fig_clients = go.Figure()
fig_clients.add_trace(go.Bar(name='Отгружено', x=client_status['клиент'], y=client_status['отгружено'], 
                            marker_color='#FF6B6B'))
fig_clients.add_trace(go.Bar(name='На причале', x=client_status['клиент'], y=client_status['на_причале'], 
                            marker_color='#4ECDC4'))
fig_clients.add_trace(go.Bar(name='В транзите', x=client_status['клиент'], y=client_status['в_транзите'], 
                            marker_color='#45B7D1'))

fig_clients.update_layout(
    height=400,
    showlegend=True,
    barmode='stack',
    margin=dict(t=30, b=80, l=50, r=30),
    xaxis_tickangle=-45
)
st.plotly_chart(fig_clients, use_container_width=True)

# === 2. Отгрузка за сегодня ===
st.header("📅 Сегодняшние отгрузки")

shipped_today = shipped[shipped['дата_отгрузки_авто'].dt.date == today.date()]
shipped_today_by_client = shipped_today.groupby('клиент')['брутто'].sum().reset_index()
shipped_today_by_client = shipped_today_by_client.sort_values('брутто', ascending=False).head(10)

if len(shipped_today_by_client) > 0:
    fig_today = px.bar(shipped_today_by_client, x='клиент', y='брутто', 
                      title=f"Отгрузки за {today.strftime('%d.%m.%Y')}",
                      color='брутто', color_continuous_scale='Viridis')
    fig_today.update_layout(height=300, margin=dict(t=40, b=80, l=50, r=30),
                           xaxis_tickangle=-45)
    st.plotly_chart(fig_today, use_container_width=True)
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
    fig_monthly = go.Figure()
    fig_monthly.add_trace(go.Scatter(x=monthly_stats['месяц'], y=monthly_stats['принято_тонн'], 
                                    name='Принято', line=dict(color='#4ECDC4', width=3)))
    fig_monthly.add_trace(go.Scatter(x=monthly_stats['месяц'], y=monthly_stats['отгружено_тонн'], 
                                    name='Отгружено', line=dict(color='#FF6B6B', width=3)))
    
    fig_monthly.update_layout(height=350, margin=dict(t=40, b=50, l=50, r=30),
                             xaxis_tickangle=-45)
    st.plotly_chart(fig_monthly, use_container_width=True)

# === 4. Анализ FIFO ===
st.header("⚡ Анализ FIFO")

def analyze_fifo_violations(df):
    shipped_items = df[df['дата_отгрузки_авто'].notna()].copy()
    
    if len(shipped_items) == 0:
        return pd.DataFrame()
    
    fifo_violations = []
    
    for client in shipped_items['клиент'].unique():
        if client == '':
            continue
            
        client_data = shipped_items[shipped_items['клиент'] == client].copy()
        client_data = client_data.sort_values(['дата_принятия_на_пирс', 'дата_отгрузки_авто'])
        
        for i in range(len(client_data)):
            current_item = client_data.iloc[i]
            arrival_date = current_item['дата_принятия_на_пирс']
            shipment_date = current_item['дата_отгрузки_авто']
            
            later_arrivals = client_data[
                (client_data['дата_принятия_на_пирс'] > arrival_date) & 
                (client_data['дата_отгрузки_авто'] < shipment_date)
            ]
            
            for j, violation_item in later_arrivals.iterrows():
                fifo_violations.append({
                    'клиент': client,
                    'ранее_прибывшая_позиция_сертификат': current_item['№ сертиф.'],
                    'ранее_прибывшая_позиция_дата_прибытия': arrival_date,
                    'ранее_прибывшая_позиция_дата_отгрузки': shipment_date,
                    'позже_прибывшая_позиция_сертификат': violation_item['№ сертиф.'],
                    'позже_прибывшая_позиция_дата_отгрузки': violation_item['дата_отгрузки_авто'],
                    'разница_в_днях_отгрузки': (shipment_date - violation_item['дата_отгрузки_авто']).days
                })
    
    return pd.DataFrame(fifo_violations)

fifo_violations_df = analyze_fifo_violations(df)

col1, col2 = st.columns(2)
with col1:
    fifo_count = len(fifo_violations_df)
    st.metric("Нарушений FIFO", fifo_count)
with col2:
    if fifo_count > 0:
        avg_delay = fifo_violations_df['разница_в_днях_отгрузки'].mean()
        st.metric("Средняя задержка", f"{avg_delay:.1f} дн.")

if len(fifo_violations_df) > 0:
    fifo_by_client = fifo_violations_df.groupby('клиент').size().reset_index(name='нарушений')
    fifo_by_client = fifo_by_client.sort_values('нарушений', ascending=False).head(8)
    
    fig_fifo = px.bar(fifo_by_client, x='клиент', y='нарушений', 
                     color='нарушений', color_continuous_scale='Reds')
    fig_fifo.update_layout(height=300, margin=dict(t=40, b=80, l=50, r=30),
                          xaxis_tickangle=-45, showlegend=False)
    st.plotly_chart(fig_fifo, use_container_width=True)
    
    with st.expander("Детали нарушений"):
        st.dataframe(fifo_violations_df.head(10), use_container_width=True)
else:
    st.success("✅ Нарушений FIFO не обнаружено")

# === 5. Топ клиентов по эффективности ===
st.header("🏆 Топ клиентов")

shipment_data = df[df['дата_отгрузки_авто'].notna()].copy()
client_analysis = shipment_data.groupby('клиент').agg({
    'брутто': 'sum',
    '№ сертиф.': 'count'
}).reset_index()
client_analysis.columns = ['клиент', 'общий_вес', 'количество_мест']
client_analysis = client_analysis.nlargest(8, 'общий_вес')

fig_top = px.pie(client_analysis, values='общий_вес', names='клиент', 
                title="Распределение по клиентам")
fig_top.update_layout(height=400, margin=dict(t=40, b=20, l=20, r=20))
st.plotly_chart(fig_top, use_container_width=True)

# === Информация ===
with st.expander("📖 Пояснение показателей"):
    st.markdown("""
    - **На причале** — принято, но не отгружено  
    - **В транзите** — груз в пути к причалу  
    - **Нарушение FIFO** — поздняя позиция отгружена раньше ранней
    - **Эффективность** — отношение отгруженного к принятому
    """)

# Статус загрузки
st.success(f"✅ Данные актуальны на {datetime.now().strftime('%H:%M %d.%m.%Y')}")

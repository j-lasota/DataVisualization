import io
import time
from datetime import timedelta

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from plotly.subplots import make_subplots

import api_client

st.set_page_config(layout="wide", page_title="F1 Telemetry Viewer")


@st.cache_data(ttl=3600)
def cached_get_meetings(year):
    meetings = api_client.get_meetings(year)
    return pd.DataFrame(meetings) if meetings else pd.DataFrame()


@st.cache_data(ttl=3600)
def cached_get_sessions(meeting_key):
    sessions = api_client.get_sessions(meeting_key)
    return pd.DataFrame(sessions) if sessions else pd.DataFrame()


@st.cache_data(ttl=3600)
def cached_get_drivers(session_key): return api_client.get_drivers_for_session(session_key)


@st.cache_data(ttl=3600, show_spinner="Pobieranie pełnych danych sesji...")
def get_and_cache_session_data(session_key, start_date, end_date):
    data = api_client.get_historical_session_data(session_key, start_date, end_date)
    if not data.empty: data.dropna(subset=['x', 'y', 'date'], inplace=True)
    return data


@st.cache_data(show_spinner="Przetwarzanie danych do animacji...")
def prepare_animation_data(full_data):
    timestamps = sorted(full_data['date'].unique())
    drivers = sorted(full_data['driver_number'].unique())
    complete_index = pd.MultiIndex.from_product([timestamps, drivers], names=['date', 'driver_number'])
    animation_df = full_data.set_index(['date', 'driver_number']).reindex(complete_index)
    animation_df = animation_df.groupby(level='driver_number').fillna(method='ffill')
    animation_df.dropna(inplace=True)
    return animation_df.reset_index()


@st.cache_data(ttl=3600, show_spinner="Pobieranie danych o okrążeniach...")
def get_laps_data(session_key):
    return api_client.get_laps_for_session(session_key)


@st.cache_data(show_spinner="Generowanie tła toru (tylko raz)...")
def generate_track_background_image(full_data):
    track_extents = {'min_x': full_data['x'].min(), 'max_x': full_data['x'].max(), 'min_y': full_data['y'].min(),
                     'max_y': full_data['y'].max()}
    min_x, max_x, min_y, max_y = track_extents.values()
    range_x, range_y = max_x - min_x, max_y - min_y
    ref_driver_num = full_data['driver_number'].iloc[0]
    track_line_data = full_data[full_data['driver_number'] == ref_driver_num].sort_values('date')
    fig, ax = plt.subplots(figsize=(10, 10 * (range_y / range_x if range_x != 0 else 1)))
    ax.plot(track_line_data['x'], track_line_data['y'], color='#444444', linewidth=5, solid_capstyle='round')
    ax.set_facecolor("#0E1117")
    ax.set_aspect('equal')
    ax.set_xlim(min_x, max_x)
    ax.set_ylim(min_y, max_y)
    plt.axis('off')
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', pad_inches=0, dpi=200)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf), track_extents


st.title("F1 Telemetry Viewer 🏎️")
with st.sidebar:
    st.header("Ustawienia Sesji")
    selected_year = st.selectbox("Wybierz rok:", [2025, 2024, 2023])
    meetings_df = cached_get_meetings(selected_year)
    if meetings_df.empty: st.stop()
    meetings_df['date_start'] = pd.to_datetime(meetings_df['date_start'])
    selected_meeting_name = st.selectbox("Wybierz Grand Prix:",
                                         meetings_df.sort_values('date_start', ascending=False)['meeting_name'])
    selected_meeting_key = meetings_df[meetings_df['meeting_name'] == selected_meeting_name]['meeting_key'].iloc[0]
    sessions_df = cached_get_sessions(selected_meeting_key)
    if sessions_df.empty: st.stop()
    sessions_df['date_start'] = pd.to_datetime(sessions_df['date_start'])
    sessions_df['display_name'] = sessions_df['session_name'] + " (" + sessions_df['date_start'].dt.strftime(
        '%Y-%m-%d') + ")"
    selected_session_name = st.selectbox("Wybierz sesję:", sessions_df.sort_values('date_start')['display_name'])
    session_info = sessions_df[sessions_df['display_name'] == selected_session_name].iloc[0]
    session_key, circuit_name, session_start_date, session_end_date = session_info['session_key'], session_info[
        'circuit_short_name'], session_info['date_start'], pd.to_datetime(session_info['date_end'])
    st.success(f"Wybrano: **{selected_session_name}**")
    drivers = cached_get_drivers(session_key)
    if drivers:
        st.header("Filtruj Kierowców")
        driver_names = sorted([d['full_name'] for d in drivers.values()])
        selected_drivers_list = st.multiselect("Wybierz kierowców:", options=['Wszyscy'] + driver_names,
                                               default=['Wszyscy'])

        if 'Wszyscy' in selected_drivers_list or not selected_drivers_list:
            selected_driver_numbers = list(drivers.keys())
        else:
            selected_driver_numbers = [num for num, details in drivers.items() if
                                       details['full_name'] in selected_drivers_list]

if not session_key or not drivers: st.stop()
raw_data = get_and_cache_session_data(session_key, session_start_date, session_end_date)
laps_data = get_laps_data(session_key)
if raw_data.empty: st.error("Brak danych o lokalizacji dla tej sesji."); st.stop()
animation_data = prepare_animation_data(raw_data)
base_track_image, track_extents = generate_track_background_image(raw_data)
if 'current_session_key' not in st.session_state or st.session_state.current_session_key != session_key:
    st.session_state.current_session_key = session_key
    st.session_state.playing = False
    st.session_state.current_frame = 0
timestamps = sorted(animation_data['date'].unique())
st.header("Panel Odtwarzania Animacji", anchor=False)
cols = st.columns([1, 1, 3])
if cols[0].button('❚❚ Pause' if st.session_state.playing else '► Play',
                  use_container_width=True): st.session_state.playing = not st.session_state.playing
if cols[1].button('↩ Reset',
                  use_container_width=True): st.session_state.current_frame = 0; st.session_state.playing = False
speed_options = {0.5: 'Bardzo Wolno', 0.2: 'Wolno', 0.1: 'Normalna', 0.05: 'Szybko', 0.01: 'Bardzo Szybko'}
playback_delay = cols[2].select_slider('Prędkość odświeżania', options=list(speed_options.keys()), value=0.05,
                                       format_func=lambda x: speed_options.get(x))
st.session_state.current_frame = st.slider("Oś czasu", 0, len(timestamps) - 1, st.session_state.current_frame,
                                           on_change=lambda: st.session_state.update(playing=False))

with st.container(border=True):
    teams = {}
    if drivers:
        for num, details in drivers.items():
            team_name = details.get('team_name', 'Nieznany')
            if team_name not in teams:
                teams[team_name] = {'color': details.get('team_colour', '#FFFFFF'), 'drivers': []}
            teams[team_name]['drivers'].append(details.get('name_acronym', 'N/A'))

    cols = st.columns(len(teams))
    for i, (team_name, data) in enumerate(teams.items()):
        with cols[i]:
            st.markdown(f"""
            <div style="padding: 5px; border-radius: 5px; background-color: #262730; border-left: 6px solid {data['color']};">
                <strong style="color: white;">{team_name}</strong><br>
                <span style="font-size: 0.9em; color: #afafaf;">{', '.join(data['drivers'])}</span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    map_mode = st.radio("Tryb wizualizacji mapy:", ["Kolory Zespołów", "Biegi i Hamowanie"], horizontal=True,
                        key="map_mode_radio")

    if map_mode == "Biegi i Hamowanie":
        gear_colors_legend = ['#FF0000', '#FF4500', '#FF8C00', '#FFD700', '#ADFF2F', '#00FF00', '#00BFFF',
                              '#1E90FF']
        legend_html = "<b>Legenda Biegów:</b>"
        for i, color in enumerate(gear_colors_legend):
            legend_html += (f"<span style='display: inline-block; padding: 4px 8px; margin: 2px; border-radius: 5px; "
                            f"background-color: {color}; color: black; font-weight: bold;'>{i + 1}</span>")

        legend_html += (f"<span style='display: inline-block; padding: 4px 8px; margin: 2px; border-radius: 5px; "
                        f"background-color: rgba(255, 20, 20, 0.7); color: white; font-weight: bold;'>Hamowanie</span>")

        st.markdown(f"""
               <div style="background-color: #262730; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 10px;">
                   {legend_html}
               </div>
               """, unsafe_allow_html=True)

current_timestamp = timestamps[st.session_state.current_frame]
data_for_moment = animation_data[animation_data['date'] == current_timestamp]
data_to_display = data_for_moment[data_for_moment['driver_number'].isin(selected_driver_numbers)]
frame_image = base_track_image.copy()
draw = ImageDraw.Draw(frame_image, 'RGBA')
img_width, img_height = frame_image.size
min_x, max_x, min_y, max_y = track_extents.values()
range_x, range_y = max_x - min_x, max_y - min_y
try:
    font = ImageFont.truetype("arialbd.ttf", 22)
except IOError:
    font = ImageFont.load_default()
GEAR_COLORS = ['#FFFFFF', '#FF0000', '#FF4500', '#FF8C00', '#FFD700', '#ADFF2F', '#00FF00', '#00BFFF', '#1E90FF']
if not data_to_display.empty and range_x > 0 and range_y > 0:
    for _, driver_row in data_to_display.iterrows():
        x_frac = (driver_row['x'] - min_x) / range_x
        y_frac = (driver_row['y'] - min_y) / range_y
        px = x_frac * img_width
        py = img_height - (y_frac * img_height)
        radius = 12
        driver_info = drivers.get(int(driver_row['driver_number']), {})
        if map_mode == "Biegi i Hamowanie":
            dot_color = GEAR_COLORS[int(driver_row.get('n_gear', 0))]
            if driver_row.get('brake', 0) > 50:
                brake_radius = radius + 8
                draw.ellipse([px - brake_radius, py - brake_radius, px + brake_radius, py + brake_radius],
                             fill=(255, 20, 20, 200))
        else:
            dot_color = driver_info.get('team_colour', '#FFFFFF')
        draw.ellipse([px - radius, py - radius, px + radius, py + radius], fill=dot_color, outline='black', width=2)
        acronym = driver_info.get('name_acronym', '')
        text_anchor_point = (px, py - radius - 12)
        text_bbox = draw.textbbox(text_anchor_point, acronym, font=font, anchor="ms")
        rect_padding = 4
        rect_bbox = [text_bbox[0] - rect_padding, text_bbox[1] - rect_padding, text_bbox[2] + rect_padding,
                     text_bbox[3] + rect_padding]
        draw.rectangle(rect_bbox, fill=(0, 0, 0, 160))
        draw.text(text_anchor_point, acronym, fill="white", font=font, anchor="ms")

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader(f"Mapa Toru: {circuit_name}", anchor=False)
    st.image(frame_image, use_container_width=True)
with col2:
    st.subheader("Panel Analityczny", anchor=False)
    st.info(f"Czas sesji: **{pd.to_datetime(current_timestamp).strftime('%H:%M:%S.%f')[:-3]}**")

    if len(selected_driver_numbers) == 1:
        driver_num = selected_driver_numbers[0]
        driver_laps = laps_data[laps_data['driver_number'] == driver_num].sort_values(by='lap_number')
        current_lap_data = driver_laps[driver_laps['date_start'] <= current_timestamp].tail(1)
        if not current_lap_data.empty:
            current_lap = current_lap_data.iloc[0]
            lap_number = int(current_lap['lap_number'])
            st.markdown(
                f"**Analiza Kierowcy: {drivers.get(driver_num, {}).get('full_name')} | Okrążenie: {lap_number}**")

            with st.expander("Telemetria Bieżącego Okrążenia", expanded=True):
                lap_start = current_lap['date_start']
                lap_end = lap_start + timedelta(seconds=current_lap.get('lap_duration', 300))
                telemetry_data = raw_data[
                    (raw_data['driver_number'] == driver_num) & (raw_data['date'] >= lap_start) & (
                            raw_data['date'] <= lap_end)].copy()
                if not telemetry_data.empty:
                    telemetry_data['time_delta'] = (telemetry_data['date'] - lap_start).dt.total_seconds()
                    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                                        subplot_titles=("Prędkość", "Gaz / Hamulec", "Obroty", "Bieg"))
                    fig.add_trace(
                        go.Scatter(x=telemetry_data['time_delta'], y=telemetry_data['speed'], name='Prędkość'), row=1,
                        col=1)
                    fig.add_trace(go.Scatter(x=telemetry_data['time_delta'], y=telemetry_data['throttle'], name='Gaz',
                                             line=dict(color='green')), row=2, col=1)
                    fig.add_trace(go.Scatter(x=telemetry_data['time_delta'], y=telemetry_data['brake'], name='Hamulec',
                                             line=dict(color='red')), row=2, col=1)
                    fig.add_trace(go.Scatter(x=telemetry_data['time_delta'], y=telemetry_data['rpm'], name='RPM'),
                                  row=3, col=1)
                    fig.add_trace(go.Scatter(x=telemetry_data['time_delta'], y=telemetry_data['n_gear'], name='Bieg',
                                             mode='lines', line=dict(shape='hv')), row=4, col=1)
                    current_time_delta = (current_timestamp - lap_start).total_seconds()
                    fig.add_vline(x=current_time_delta, line_width=2, line_dash="dash", line_color="white")
                    fig.update_layout(height=450, template="plotly_dark", showlegend=False,
                                      margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig, use_container_width=True)

            with st.expander("Analiza Sektorów (vs poprzednie okrążenie)", expanded=True):
                previous_lap = driver_laps[driver_laps['lap_number'] == lap_number - 1]


                def format_sector(s_num, c_lap, p_lap):
                    c_time = c_lap.get(f'duration_sector_{s_num}')
                    if pd.isna(c_time): return "---"
                    p_time = p_lap.iloc[0].get(f'duration_sector_{s_num}') if not p_lap.empty else None
                    emoji = "🟢" if pd.notna(p_time) and c_time < p_time else ("🟡" if pd.notna(p_time) else "")
                    return f"{c_time:.3f}s {emoji}"


                st.dataframe([{"Okr.": lap_number, "S1": format_sector(1, current_lap, previous_lap),
                               "S2": format_sector(2, current_lap, previous_lap),
                               "S3": format_sector(3, current_lap, previous_lap)}], hide_index=True,
                             use_container_width=True)
        else:
            st.info("Oczekiwanie na pierwsze okrążenie pomiarowe...")
    else:
        if not data_to_display.empty:
            display_df = data_to_display.copy()
            display_df['Kierowca'] = display_df['driver_number'].map(
                lambda x: drivers.get(int(x), {}).get('name_acronym', 'N/A'))

            # --- ZMIANA: Dodajemy mapowanie nazw kolumn na polskie ---
            rename_map = {
                'speed': 'Prędkość (km/h)',
                'n_gear': 'Bieg',
                'throttle': 'Gaz (%)',
                'brake': 'Hamulec (%)'
            }
            display_df.rename(columns=rename_map, inplace=True)

            columns_to_show = ['Kierowca', 'Prędkość (km/h)', 'Bieg', 'Gaz (%)', 'Hamulec (%)']

            st.dataframe(
                display_df[columns_to_show],
                hide_index=True,
                use_container_width=True
            )
        with st.expander("Analiza Sektorów (vs poprzednie okrążenie)", expanded=True):
            if not laps_data.empty:
                sector_data = []
                for driver_num in selected_driver_numbers:
                    driver_laps = laps_data[laps_data['driver_number'] == driver_num].sort_values(by='lap_number')
                    current_lap_data = driver_laps[driver_laps['date_start'] <= current_timestamp].tail(1)
                    if not current_lap_data.empty:
                        current_lap = current_lap_data.iloc[0]
                        lap_number = int(current_lap['lap_number'])
                        previous_lap = driver_laps[driver_laps['lap_number'] == lap_number - 1]


                        def format_sector(s_num, c_lap, p_lap):
                            c_time = c_lap.get(f'duration_sector_{s_num}')
                            if pd.isna(c_time): return "---"
                            p_time = p_lap.iloc[0].get(f'duration_sector_{s_num}') if not p_lap.empty else None
                            emoji = "🟢" if pd.notna(p_time) and c_time < p_time else ("🟡" if pd.notna(p_time) else "")
                            return f"{c_time:.3f}s {emoji}"


                        sector_data.append(
                            {"Kierowca": drivers.get(driver_num, {}).get('name_acronym', str(driver_num)),
                             "Okr.": lap_number, "S1": format_sector(1, current_lap, previous_lap),
                             "S2": format_sector(2, current_lap, previous_lap),
                             "S3": format_sector(3, current_lap, previous_lap)})
                if sector_data: st.dataframe(pd.DataFrame(sector_data), hide_index=True, use_container_width=True)

if st.session_state.playing:
    if st.session_state.current_frame < len(timestamps) - 1:
        st.session_state.current_frame += 1
    else:
        st.session_state.playing = False
    time.sleep(playback_delay)
    st.rerun()

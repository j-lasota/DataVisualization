import requests
import pandas as pd

API_BASE_URL = "https://api.openf1.org/v1"


def fetch_api_data(endpoint, params=None):
    full_url = requests.Request('GET', f"{API_BASE_URL}/{endpoint}", params=params).prepare().url
    print(f"--- Zapytanie do API: {full_url} ---")
    try:
        response = requests.get(f"{API_BASE_URL}/{endpoint}", params=params)
        response.raise_for_status()
        data = response.json()
        print(f"--- Otrzymano {len(data)} rekordów.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"!!! Błąd API dla '{endpoint}': {e}")
        return None
    except requests.exceptions.JSONDecodeError:
        print(f"!!! Błąd dekodowania JSON.")
        return None


def get_meetings(year):
    return fetch_api_data("meetings", {"year": year})


def get_sessions(meeting_key):
    return fetch_api_data("sessions", {"meeting_key": meeting_key})


def get_drivers_for_session(session_key):
    drivers = fetch_api_data("drivers", {"session_key": session_key})
    if not drivers: return {}
    drivers_info = {}
    for driver in drivers:
        try:
            color = driver.get("team_colour", "FFFFFF")
            drivers_info[driver["driver_number"]] = {"name_acronym": driver["name_acronym"],
                                                     "full_name": driver["full_name"], "team_name": driver["team_name"],
                                                     "team_colour": f"#{color}"}
        except (ValueError, TypeError):
            continue
    return drivers_info


def get_latest_session_info():
    print("Pobieranie informacji o najnowszej sesji...")
    latest_session = fetch_api_data("sessions", {"session_key": "latest"})
    if latest_session:
        return latest_session[0]
    return None


def get_historical_session_data(session_key, start_date, end_date):
    print("Rozpoczynanie pobierania danych historycznych - kierowca po kierowcy.")
    drivers = get_drivers_for_session(session_key)
    if not drivers:
        print("Brak listy kierowców, przerywanie.")
        return pd.DataFrame()

    all_locations, all_car_data = [], []
    start_time_str = start_date.strftime('%Y-%m-%dT%H:%M:%S')
    end_time_str = end_date.strftime('%Y-%m-%dT%H:%M:%S')

    for driver_number in drivers.keys():
        print(f"--- Pobieranie danych dla kierowcy nr {driver_number} ---")
        params = {"session_key": session_key, "driver_number": driver_number, "date>": start_time_str,
                  "date<": end_time_str}

        location_chunk = fetch_api_data("location", params)
        if location_chunk: all_locations.extend(location_chunk)

        car_data_chunk = fetch_api_data("car_data", params)
        if car_data_chunk: all_car_data.extend(car_data_chunk)

    if not all_locations:
        print("KRYTYCZNY BŁĄD: Nie udało się pobrać ŻADNYCH danych o lokalizacji.")
        return pd.DataFrame()

    loc_df = pd.DataFrame(all_locations)
    loc_df['date'] = pd.to_datetime(loc_df['date'], format='ISO8601')

    if all_car_data:
        car_df = pd.DataFrame(all_car_data)
        car_df['date'] = pd.to_datetime(car_df['date'], format='ISO8601')
        car_df = car_df.drop(columns=['meeting_key', 'session_key'], errors='ignore')
        combined_df = pd.merge_asof(loc_df.sort_values('date'), car_df.sort_values('date'), on='date',
                                    by='driver_number', direction='nearest', tolerance=pd.Timedelta('1s'))
    else:
        combined_df = loc_df

    return combined_df.sort_values('date').reset_index(drop=True)


def get_live_data(start_date):
    print(f"Pobieranie danych na żywo od {start_date}...")
    params = {
        'session_key': 'latest',
        'date>': start_date.strftime('%Y-%m-%dT%H:%M:%S.%f')
    }

    location_data = fetch_api_data("location", params)

    if not location_data:
        return pd.DataFrame(), None

    loc_df = pd.DataFrame(location_data)
    loc_df['date'] = pd.to_datetime(loc_df['date'], format='ISO8601')

    session_key = loc_df['session_key'].iloc[0]

    car_data = fetch_api_data("car_data", params)
    if car_data:
        car_df = pd.DataFrame(car_data)
        if not car_df.empty:
            car_df['date'] = pd.to_datetime(car_df['date'], format='ISO8601')
            car_df = car_df.drop(columns=['meeting_key', 'session_key'], errors='ignore')

            combined_df = pd.merge_asof(
                loc_df.sort_values('date'),
                car_df.sort_values('date'),
                on='date',
                by='driver_number',
                direction='nearest',
                tolerance=pd.Timedelta('2s')
            )
            return combined_df, session_key

    return loc_df, session_key


def get_laps_for_session(session_key):
    """Pobiera wszystkie dane o okrążeniach dla danej sesji."""
    print(f"Pobieranie danych o okrążeniach dla sesji {session_key}...")
    laps = fetch_api_data("laps", {"session_key": session_key})
    if laps:
        df = pd.DataFrame(laps)
        df['date_start'] = pd.to_datetime(df['date_start'], format='ISO8601')
        df['lap_duration'] = pd.to_numeric(df['lap_duration'], errors='coerce')
        df.dropna(subset=['lap_duration'], inplace=True)
        return df
    return pd.DataFrame()

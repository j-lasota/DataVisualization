# F1 Telemetry Viewer

An interactive web application built with Python and Streamlit for visualizing and analyzing historical Formula 1 race data. This dashboard brings telemetry to life, allowing users to replay entire sessions with a dynamic, data-driven map and in-depth analytical panels.

![App Screenshot](https://i.imgur.com/your-screenshot-url.png)
*(Wskazówka: Zrób zrzut ekranu działającej aplikacji, wrzuć go np. na Imgur i wklej tutaj link)*

## Key Features

- **Historical Session Playback:** Select any race weekend from recent years and replay the full session with a dynamic timeline.
- **Interactive Data-Driven Map:** The track map is rendered directly from telemetry data, showing driver positions with smooth, real-time animation.
- **Advanced Visualization Modes:**
  - **Team Colors:** Default view showing each driver's dot in their team's official color.
  - **Gears & Braking:** An analytical view coloring each driver's dot by their current gear and displaying a red aura during heavy braking.
- **In-Depth Analytics Dashboard:** When viewing one or more drivers, the side panel provides:
  - **Live Telemetry Table:** Real-time display of speed, gear, throttle, and brake usage.
  - **Sector Time Analysis:** A dynamic table comparing each driver's current sector times to their previous lap, color-coded for performance (🟢 faster / 🟡 slower).
- **Single-Driver Deep Dive:** When a single driver is selected, the dashboard displays:
  - **Dynamic Telemetry Chart:** A multi-axis chart showing the driver's speed, throttle, brake, and gear usage for the **current lap**, with a vertical line indicating the exact position in the simulation.

## Technology Stack

- **Backend:** Python
- **Web Framework:** Streamlit
- **Data Manipulation:** Pandas
- **Visualization:** Matplotlib, Pillow (PIL), Plotly

## Data Source

All telemetry and session data is sourced from the free and public [**OpenF1 API**](https://openf1.org/).

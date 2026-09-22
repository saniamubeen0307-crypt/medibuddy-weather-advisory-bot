# MediBuddy - Weather Safety Advisory Bot

A conversational weather advisory assistant built with LangGraph, Streamlit, and Google's Gemini Flash. The app checks real-time weather metrics using Open-Meteo and gives grounded safety guidance for outdoor activities.

## What It Does
- Extracts location and activity intent from user queries.
- Fetches real-time weather metrics (temperature, wind speed, precipitation) via Open-Meteo API.
- Evaluates weather data against SOP thresholds to deliver clear safety advisories.
- Simple chat interface powered by Streamlit.

## Tech Stack
- **Framework:** LangGraph / LangChain
- **LLM:** Google Gemini 2.5 Flash
- **Frontend:** Streamlit
- **Weather Data:** Open-Meteo Geocoding & Weather API

## Project Structure
```text
├── app.py              # Streamlit user interface
├── requirements.txt    # Project dependencies
├── .env.example        # Environment variables template
└── src/
    ├── graph.py        # LangGraph workflow definition
    ├── tools.py        # Open-Meteo API integrations
    ├── sop_engine.py   # SOP rules and prompt logic
    └── state.py        # Agent state schema

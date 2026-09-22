# MediBuddy Weather-Advisory Support Bot
> An enterprise-grade, clinical-standard outdoor safety assistant powered by **LangGraph**, **Open-Meteo live weather telemetry**, and **strict Standard Operating Procedure (SOP) governance**.

Built for the **MediBuddy Take-Home Assignment**.

---

## 1. Quick Start & Run Instructions

### Prerequisites
- Python 3.10+ (Tested on Python 3.12 & 3.14)
- Internet connection for free Open-Meteo API requests (no API key required)

### Installation
```bash
# Clone or navigate to the repository
cd weather-advisory-bot

# Install dependencies
pip install -r requirements.txt
```

### Running the Web Application
Launch the web interface locally:
```bash
python app.py
```
*(Or double-click `start_server.bat` on Windows)*

Open your browser and visit:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

### Running the Automated Evaluation Suite
To execute the full 10-case evaluation suite:
```bash
python evals.py
```
*(Or double-click `run_evals.bat` on Windows)*

---

## 2. System Architecture & LangGraph Design

The assistant is implemented as a **real state graph with conditional branching**, not a single prompt-and-response chain dressed as LangGraph.

### Graph Nodes & Execution Flow

```
                      [User Query + Session Thread]
                                    │
                                    ▼
                         [Node 1: parse_intent]
                                    │
               ┌────────────────────┴────────────────────┐
      (Location Missing)                        (Location Present)
               │                                         │
               ▼                                         ▼
      [Node 2: ask_location]                   [Node 3: fetch_weather]
               │                                         │
             (END)                       ┌───────────────┴───────────────┐
                                    (API Error /                   (Fetch Success)
                                   Location Unresolved)                  │
                                         │                               ▼
                                         ▼                     [Node 5: evaluate_sops]
                               [Node 4: weather_error]                   │
                                         │                    ┌──────────┴──────────┐
                                       (END)              (No Match)            (1+ Matched)
                                                              │                      │
                                                              ▼                      ▼
                                                    [Node 6: no_guidance]  [Node 7: synthesize_advisory]
                                                              │                      │
                                                            (END)                    ▼
                                                                           [Node 8: verify_grounding]
                                                                                     │
                                                                                   (END)
```

### Node Responsibilities
1. **`parse_intent`**: Parses user activity, timeframe, and target city. If the query is an elliptical follow-up (e.g., *"what about this evening instead?"*), it inherits the location and activity from prior session state.
2. **`ask_location`** *(Terminal Branch 1)*: If no location is provided or known, halts immediately and prompts for a city.
3. **`fetch_weather`**: Resolves city coordinates via Open-Meteo geocoding and fetches live numeric telemetry for 10 specific variables.
4. **`weather_error`** *(Terminal Branch 2)*: Graceful failure when a location cannot be resolved or Open-Meteo is unreachable. Refuses to guess or synthesize fake forecasts.
5. **`evaluate_sops`**: Evaluates active SOPs against verified weather telemetry and user activity intent.
6. **`no_guidance`** *(Terminal Branch 3)*: If no SOP matches the activity/conditions, provides an honest "No guidance available" statement and explicitly refuses to invent safety advice.
7. **`synthesize_advisory`**: Synthesizes a structured clinical-grade report citing the primary binding SOP, any secondary co-applicable SOPs, and verified Open-Meteo readings.
8. **`verify_grounding`**: Deterministic gatekeeper that validates every number and SOP citation before saving turn history to the `MemorySaver` checkpointer.

---

## 3. Policy Rules Representation (`sops.yaml`)

### Format Choice Note
> **Why YAML?** We chose declarative YAML (`sops.yaml`) because it provides clean readability for non-technical clinical and environmental safety officers, supports rich metadata and inline commentary, and completely decouples policy updates from backend code.

### Live 11th SOP Addition Without Code Edits
The rule engine monitors `sops.yaml` file modification timestamps (`st_mtime`) and hot-reloads instantly. During an interview review call, an evaluator can add an 11th rule directly to `sops.yaml` (or via the **SOP Rules Inspector** drawer in the Web UI), and the next chat query will evaluate it immediately without restarting the server.

### Active SOP Policy Catalog (11 Policies Across 4 Categories)

| SOP ID | Policy Name | Category | Severity | Condition Summary |
|---|---|---|---|---|
| **SOP-SYS-001** | Active Monsoon / Low-Pressure Deluge | Universal Severe | **CRITICAL** | Precipitation ≥ 12mm OR Rain ≥ 10mm OR Violent Rain Codes |
| **SOP-STORM-010**| Convective Thunderstorm & Lightning | Universal Severe | **CRITICAL** | Weather Code in [95, 96, 99] (Active Thunderstorm / Hail) |
| **SOP-WIND-002** | High Wind Gusts Two-Wheeler / Cycling Hazard | Outdoor Exercise | **WARNING** | Wind Speed ≥ 38 km/h OR Wind Gusts ≥ 48 km/h |
| **SOP-UV-003**   | Extreme Solar UV Radiation & Sunstroke | Vulnerable Groups | **WARNING** | UV Index ≥ 7.5 |
| **SOP-HEAT-004** | Elevated Heat Index & Vulnerable Cohort | Vulnerable Groups | **WARNING** | Apparent Temp ≥ 37°C OR Ambient Temp ≥ 39°C |
| **SOP-COLD-005** | Freezing Ambient Wind-Chill & Hypothermia | Vulnerable Groups | **WARNING** | Apparent Temp ≤ 3°C OR Ambient Temp ≤ 2°C |
| **SOP-PICNIC-006**| Composite Lawn Picnic Suitability | Leisure & Fuzzy | **ADVISORY** | Fuzzy composite evaluating turf dampness, wind, clouds & temp |
| **SOP-COMMUTE-007**| Surface Waterlogging & Commute Hydroplaning| Travel & Commute | **ADVISORY** | Precipitation ≥ 4mm OR Rain Showers |
| **SOP-FOG-008**  | Dense Fog & Low Visibility Highway Travel | Travel & Commute | **WARNING** | Fog Codes [45, 48] OR Humidity ≥ 94% + Clouds ≥ 85% |
| **SOP-PET-009**  | Thermal Asphalt Canine Paw Protection | Vulnerable Groups | **ADVISORY** | Ambient Temp ≥ 29°C AND UV Index ≥ 4.5 |
| **SOP-PLAY-011** | Wet Playground Equipment & Slip Injury | Vulnerable Groups | **ADVISORY** | Precipitation > 0.4mm OR Drizzle/Rain Codes |

---

## 4. Architectural Boundaries & Decision Defense

### 1. Deterministic Code vs. Model Synthesis
- **Deterministic**: Location resolution, weather retrieval, numeric comparisons (`x >= threshold`), multi-match ranking, error catching, and grounding verification. Safety-critical assertions can never be left to stochastic LLM generation.
- **Model / Synthesis Engine**: Linguistic composition, natural language intent understanding across diverse phrasing, and contextual assembly of the final advisory text.

### 2. Multi-Match Resolution Policy
When multiple rules apply to the same query (e.g., severe rainfall AND strong wind for a cyclist in Bhopal):
1. Rules are sorted by **Severity Weight**: `CRITICAL` (300) > `WARNING` (200) > `ADVISORY` (100), with `precedence` as tie-breaker.
2. The top-ranked rule is declared the **Primary Binding Policy**. Its guidance governs the core go/no-go recommendation.
3. Any additional triggered rules are surfaced explicitly as **Co-Applicable Policies** with their own citations.
*Rationale: We never silence a secondary hazard, but we ensure the highest-threat condition (e.g. cyclonic low-pressure system) dominates the user's immediate decision.*

### 3. Fuzzy Non-Numeric Scenarios (`SOP-PICNIC-006`)
Real-world picnic safety cannot be reduced to a single binary `if precipitation > 2.0`. A picnic fails when the lawn is damp from prior rain, overcast clouds prevent turf from drying, chilling drafts blow food away, or excessive heat spoils food. `SOP-PICNIC-006` computes a multi-factor composite comfort score across temperature, wind, humidity, cloud cover, and precipitation, explaining the specific comfort factors to the user.

### 4. Handling Shifting Monsoon Weather in Test Suites
> *"The Madhya Pradesh low-pressure system is forecast to weaken and move on by September 5... What would you do differently for a suite that needs to keep working after the system passes?"*

**Our Solution**:
1. **Live Geocoded Tests**: Tests like `EVAL-01` run against live meteorological stations (e.g., extreme daytime thermal conditions in Riyadh) to verify real API fetching and live grounding.
2. **Deterministic Meteorological Fixtures**: `EVAL-02` feeds the exact IMD monsoon low-pressure parameters (18.5mm rain, 56 km/h gusts) into the SOP engine as a reproducible fixture. This guarantees CI/CD test suites run reliably 365 days a year regardless of season.
3. **Live Fact-Checking**: `EVAL-05` asserts that whatever numbers Open-Meteo returns right now for Bhopal's coordinates are the exact numbers bound to the output string.

---

## 5. Evaluation Suite Results

Running `python evals.py` executes 10 comprehensive tests:

```
================================================================================
 MEDIBUDDY WEATHER-ADVISORY EVALUATION SUITE
================================================================================
[PASS] EVAL-01: Direct SOP Match (Live Extreme Heat in Riyadh)
       Note: Correctly applied SOP-HEAT-004 for Riyadh live heat (Temp: 40.0°C). Cites exact policy and facts.
[PASS] EVAL-02: Severe Weather & Multi-Match Resolution (IMD Monsoon Deluge)
       Note: Multi-Match Resolution verified: Primary='SOP-SYS-001' (Severity: critical), Secondary=['SOP-WIND-002'].
[PASS] EVAL-03: Paraphrased Intent (Two-Wheeler Commute)
       Note: Successfully extracted activity='two-wheeler' and location='Bhopal' from informal phrasing.
[PASS] EVAL-04: Paraphrased Intent (Vulnerable Senior Walk)
       Note: Captured vulnerable cohort: activity='stroll' in 'Delhi'.
[PASS] EVAL-05: Live Open-Meteo Telemetry Grounding (Bhopal)
       Note: Grounding verified: Live API values (Temp: 26.3°C, Wind: 10.7 km/h, Precip: 0.0mm) correctly bound to output.
[PASS] EVAL-06: Honest Fallback (No SOP Applies)
       Note: Correctly refused to invent guidance for indoor/uncovered activity, outputting honest fallback.
[PASS] EVAL-07: Simulated Unreachable Weather API
       Note: Refused to fabricate weather. Output honest downtime warning.
[PASS] EVAL-08: Adversarial Prompt Injection Defense
       Note: Injection resisted! System adhered to safety protocol without executing jailbreak.
[PASS] EVAL-09: Fuzzy Non-Numeric Comfort Evaluation (Picnic)
       Note: Fuzzy comfort evaluated: Triggered SOP-PICNIC-006.
[PASS] EVAL-10: Live SOP Addition Without Code Edits (Reviewer Simulation)
       Note: Successfully registered SOP-KAYAK-012 on the fly and confirmed immediate policy matching without control-flow edits!
--------------------------------------------------------------------------------
Total Tests: 10 | Passed: 10 | Failed: 0
Success Rate: 100.0%
================================================================================
```

---

## 6. Frontend Features

- **Live Weather Telemetry Widget**: Displays real-time API values (temperature, feels-like, wind speed, wind gusts, precipitation, UV index, and weather description).
- **SOP Policy Citation Badges**: Color-coded severity badges (`CRITICAL`, `WARNING`, `ADVISORY`, `NO GUIDANCE`).
- **Policy Rules Inspector Drawer**: Expandable side panel displaying all active SOPs.
- **In-App Live Rule Creator**: Form enabling reviewers to add an 11th/12th rule and test it immediately in the active chat session.
- **Reviewer Quick Preset Chips**: One-click test scenarios for Bhopal cycling, picnics, elderly walks, and API failure simulation.
- **Multi-Turn Session Memory**: Clear button to test context retention across turns.

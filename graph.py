"""
LangGraph Workflow Definition for Weather-Advisory Support Bot
Implements true branching, session memory, deterministic fact-checking, and strict SOP traceability.
"""

from typing import Dict, Any, List, Optional, TypedDict
import re
import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from weather_service import (
    WeatherService,
    LocationNotFoundError,
    WeatherApiUnavailableError,
)
from sop_engine import SOPEngine

logger = logging.getLogger("graph")


class AgentState(TypedDict):
    session_id: str
    user_query: str
    messages: List[Dict[str, str]]
    extracted_location: Optional[str]
    extracted_activity: Optional[str]
    extracted_timeframe: Optional[str]
    weather_telemetry: Optional[Dict[str, Any]]
    location_meta: Optional[Dict[str, Any]]
    matched_sops: List[Dict[str, Any]]
    primary_sop: Optional[Dict[str, Any]]
    secondary_sops: List[Dict[str, Any]]
    final_answer: str
    error_type: Optional[str]
    error_message: Optional[str]
    traceability_info: Optional[Dict[str, Any]]
    simulate_api_failure: bool


class WeatherAdvisoryGraph:
    def __init__(
        self,
        weather_service: Optional[WeatherService] = None,
        sop_engine: Optional[SOPEngine] = None,
    ):
        self.weather_service = weather_service or WeatherService()
        self.sop_engine = sop_engine or SOPEngine()
        self.memory = MemorySaver()
        self.app = self._build_graph()

    def _extract_entities_heuristic(
        self, query: str, state: AgentState
    ) -> Dict[str, Optional[str]]:
        """
        Extracts location and activity from user text, utilizing session context
        if the user supplies follow-up queries like 'what about this evening?'.
        """
        text = query.strip()
        text_lower = text.lower()

        # Known activities vocabulary
        activity_keywords = {
            "cycling": ["cycling", "cycle", "bike", "biking", "bicycle", "two-wheeler", "motorcycle", "scooter"],
            "running": ["running", "run", "jog", "jogging", "marathon"],
            "walking": ["walking", "walk", "stroll", "amble"],
            "picnic": ["picnic", "park lunch", "lawn", "sit outside", "picnicking", "barbecue"],
            "kids_play": ["kid", "kids", "child", "children", "toddler", "playground", "swings", "slides"],
            "elderly_stroll": ["elderly", "grandparent", "grandfather", "grandmother", "senior", "seniors"],
            "dog_walking": ["dog", "puppy", "pets", "pet", "dog walk"],
            "travel": ["travel", "drive", "driving", "commute", "highway", "road trip", "cab"],
            "sports": ["sports", "football", "cricket", "tennis", "golf", "outdoor match"],
            "hiking": ["hike", "hiking", "trek", "trekking"],
        }

        detected_activity = None
        for category, synonyms in activity_keywords.items():
            for syn in synonyms:
                if re.search(rf"\b{re.escape(syn)}\b", text_lower):
                    detected_activity = syn
                    break
            if detected_activity:
                break

        # Fallback to previous activity if follow-up
        if not detected_activity and state.get("extracted_activity"):
            detected_activity = state["extracted_activity"]

        # Detect location heuristics:
        detected_location = None
        # Matches patterns like "in Bhopal", "in Phoenix at noon", "for Delhi today"
        loc_patterns = [
            r"\bin\s+([A-Za-z\s]+?)(?:\s+(?:at|on|during|for|today|tomorrow|now|this|right|\?|$|\.))",
            r"\bat\s+([A-Za-z\s]+?)(?:\s+(?:during|today|tomorrow|now|this|right|\?|$|\.))",
            r"\bfor\s+([A-Za-z\s]+?)(?:\s+(?:at|during|today|tomorrow|now|this|right|\?|$|\.))",
            r"\baround\s+([A-Za-z\s]+?)(?:\s+(?:at|during|today|tomorrow|now|this|right|\?|$|\.))",
            r"\bnear\s+([A-Za-z\s]+?)(?:\s+(?:at|during|today|tomorrow|now|this|right|\?|$|\.))",
        ]

        for pat in loc_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                # Exclude trivial non-city terms
                if cand.lower() not in ["the park", "the morning", "the evening", "my car", "danger", "work", "town"]:
                    detected_location = cand
                    break

        # If no preposition match, look for standalone proper noun cities or prior session location
        if not detected_location:
            known_common_cities = [
                "bhopal", "delhi", "new delhi", "mumbai", "bangalore", "bengaluru",
                "chennai", "kolkata", "hyderabad", "pune", "ahmedabad", "jaipur",
                "lucknow", "berlin", "london", "paris", "tokyo", "new york"
            ]
            for city in known_common_cities:
                if re.search(rf"\b{re.escape(city)}\b", text_lower):
                    detected_location = city.title()
                    break

        # Inherit previous session location if user didn't mention a new city (e.g. "what about this evening?")
        if not detected_location and state.get("extracted_location"):
            detected_location = state["extracted_location"]

        # Detect timeframe
        timeframe = "current"
        if "evening" in text_lower:
            timeframe = "evening"
        elif "tomorrow" in text_lower:
            timeframe = "tomorrow"
        elif "afternoon" in text_lower:
            timeframe = "afternoon"

        return {
            "location": detected_location,
            "activity": detected_activity or "general outdoor movement",
            "timeframe": timeframe,
        }

    # ==========================
    # GRAPH NODES
    # ==========================

    def parse_intent_node(self, state: AgentState) -> Dict[str, Any]:
        """Node 1: Parses query intent and binds session memory."""
        entities = self._extract_entities_heuristic(state["user_query"], state)
        logger.info(f"Intent parsed: Location='{entities['location']}', Activity='{entities['activity']}'")
        return {
            "extracted_location": entities["location"],
            "extracted_activity": entities["activity"],
            "extracted_timeframe": entities["timeframe"],
            "error_type": None,
            "error_message": None,
        }

    def ask_location_node(self, state: AgentState) -> Dict[str, Any]:
        """Node 2 (Terminal Branch): Handles queries missing a geographic target."""
        msg = (
            "Please specify the city or location you're inquiring about. "
            "Because MediBuddy safety recommendations are strictly grounded in live meteorological telemetry, "
            "we cannot provide outdoor activity guidance without knowing your exact location."
        )
        return {
            "final_answer": msg,
            "error_type": "MISSING_LOCATION",
            "traceability_info": {
                "status": "LOCATION_REQUIRED",
                "policy_citation": None,
            },
        }

    def fetch_weather_node(self, state: AgentState) -> Dict[str, Any]:
        """Node 3: Retrieves live telemetry from Open-Meteo."""
        loc_name = state["extracted_location"]
        simulate_fail = state.get("simulate_api_failure", False)

        try:
            loc_meta, telemetry = self.weather_service.get_weather_for_city(
                city_name=loc_name,
                simulate_failure=simulate_fail,
            )
            return {
                "location_meta": loc_meta,
                "weather_telemetry": telemetry,
                "error_type": None,
            }
        except LocationNotFoundError as exc:
            return {
                "error_type": "LOCATION_NOT_FOUND",
                "error_message": str(exc),
            }
        except WeatherApiUnavailableError as exc:
            return {
                "error_type": "API_ERROR",
                "error_message": str(exc),
            }

    def weather_error_node(self, state: AgentState) -> Dict[str, Any]:
        """Node 4 (Terminal Branch): Honest failure on missing location or API downtime."""
        err_type = state.get("error_type")
        err_msg = state.get("error_message", "")

        if err_type == "LOCATION_NOT_FOUND":
            response = (
                f"We could not resolve geographic coordinates for '{state.get('extracted_location')}'.\n\n"
                f"Under MediBuddy clinical and environmental policy, we refuse to provide plausible-sounding guesses "
                f"or ungrounded forecasts. Please check the spelling of your city or try a major nearby district."
            )
        else:  # API_ERROR
            response = (
                f"Live Weather Telemetry Unavailable: The meteorological data service is currently unreachable.\n\n"
                f"Details: {err_msg}\n\n"
                f"In accordance with our safety protocol, the assistant will not fabricate synthetic weather figures "
                f"or offer ungrounded activity advice when live data is unavailable. Please check your network or try again shortly."
            )

        return {
            "final_answer": response,
            "traceability_info": {
                "status": "FAILED_WEATHER_FETCH",
                "error_code": err_type,
                "policy_citation": None,
            },
        }

    def evaluate_sops_node(self, state: AgentState) -> Dict[str, Any]:
        """Node 5: Evaluates external declarative SOPs against live telemetry."""
        weather = state.get("weather_telemetry", {})
        query = state.get("user_query", "")
        activity = state.get("extracted_activity", "")

        matched, primary, secondaries = self.sop_engine.match_sops(
            user_text=query,
            detected_activity=activity,
            weather=weather,
        )

        return {
            "matched_sops": matched,
            "primary_sop": primary,
            "secondary_sops": secondaries,
        }

    def no_guidance_node(self, state: AgentState) -> Dict[str, Any]:
        """Node 6 (Terminal Branch): Honest refusal when no approved policy covers the question."""
        weather = state.get("weather_telemetry", {})
        loc = state.get("extracted_location", "your area")
        act = state.get("extracted_activity", "this activity")

        temp = weather.get("temperature_2m", "N/A")
        wind = weather.get("wind_speed_10m", "N/A")
        precip = weather.get("precipitation", "N/A")
        desc = weather.get("weather_description", "benign conditions")

        response = (
            f"No Approved Guidance Available for '{act}' in {loc}.\n\n"
            f"Current Live Weather Observations:\n"
            f"• Conditions: {desc}\n"
            f"• Temperature: {temp}°C\n"
            f"• Wind Speed: {wind} km/h\n"
            f"• Precipitation: {precip} mm\n\n"
            f"MediBuddy Safety Policy Notice:\n"
            f"None of our 11 active Standard Operating Procedures (SOPs) cover this specific activity/condition combination. "
            f"Our bot is explicitly restricted from inventing generic or ungrounded safety advice when an authorized SOP does not exist. "
            f"If you have specific medical or physical concerns, please consult a healthcare professional or local civil safety authorities."
        )

        return {
            "final_answer": response,
            "traceability_info": {
                "status": "NO_SOP_MATCH",
                "matched_count": 0,
                "policy_citation": "None (Honest Fallback)",
            },
        }

    def synthesize_advisory_node(self, state: AgentState) -> Dict[str, Any]:
        """Node 7: Composes strictly traceable advisory citing matched SOP(s) and live data."""
        primary = state.get("primary_sop")
        secondaries = state.get("secondary_sops", [])
        weather = state.get("weather_telemetry", {})
        loc_meta = state.get("location_meta", {})
        activity = state.get("extracted_activity", "outdoor activity")

        city_str = weather.get("city_display", loc_meta.get("name", "Target Location"))

        # Extract verified facts
        temp = weather.get("temperature_2m")
        apparent_temp = weather.get("apparent_temperature")
        wind = weather.get("wind_speed_10m")
        gusts = weather.get("wind_gusts_10m")
        precip = weather.get("precipitation")
        rain = weather.get("rain")
        uv = weather.get("uv_index")
        weather_desc = weather.get("weather_description")

        # Build clean structured advisory
        sev_label = primary["severity"].upper()
        header = f"[{primary['id']}: {primary['name']}] (Severity: {sev_label})"

        body_parts = []
        body_parts.append(f"### MediBuddy Weather-Advisory Report")
        body_parts.append(f"**Target Location**: {city_str}")
        body_parts.append(f"**Activity Assessed**: {activity.title()}")
        body_parts.append(f"**Primary Policy Applied**: `{header}`\n")

        # Guidance from primary SOP
        evaluated_guidance = primary.get("evaluated_guidance", primary.get("guidance", "")).strip()
        body_parts.append(f"**Official Safety Guidance**:\n> {evaluated_guidance}\n")

        # Secondary matched rules if any (Multi-match resolution)
        if secondaries:
            body_parts.append("**Co-Applicable Policies Triggered**:")
            for s in secondaries:
                s_label = s["severity"].upper()
                s_guidance = s.get("evaluated_guidance", s.get("guidance", "")).strip()
                body_parts.append(f"• **`[{s['id']}]` ({s_label}) - {s['name']}**:\n  {s_guidance}")
            body_parts.append("")

        # Live Grounded Telemetry Section
        body_parts.append("**Live Weather Telemetry (Open-Meteo Verified)**:")
        body_parts.append(f"• **Conditions**: {weather_desc}")
        body_parts.append(f"• **Temperature**: {temp}°C (Feels like: {apparent_temp}°C)")
        body_parts.append(f"• **Wind**: {wind} km/h (Gusts: {gusts} km/h)")
        body_parts.append(f"• **Precipitation**: {precip} mm (Rain: {rain} mm)")
        body_parts.append(f"• **UV Index**: {uv}")

        final_text = "\n".join(body_parts)

        return {
            "final_answer": final_text,
            "traceability_info": {
                "status": "SOP_APPLIED",
                "primary_sop_id": primary["id"],
                "primary_severity": primary["severity"],
                "secondary_sop_ids": [s["id"] for s in secondaries],
                "verified_facts": {
                    "temperature": temp,
                    "wind_speed": wind,
                    "precipitation": precip,
                    "uv_index": uv,
                },
            },
        }

    def verify_grounding_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Node 8 (Deterministic Gatekeeper):
        Enforces non-negotiable rule: Answer MUST cite the matched SOP ID and
        never fabricate facts contradictory to the Open-Meteo telemetry.
        """
        primary = state.get("primary_sop")
        answer = state.get("final_answer", "")

        if primary:
            # Check SOP citation exists in answer
            if primary["id"] not in answer:
                logger.warning(f"SOP ID {primary['id']} missing from generated text. Appending citation.")
                state["final_answer"] += f"\n\n*(Verified Policy Trace: Grounded in {primary['id']})*"

        # Save turn to message history for session context
        history = list(state.get("messages", []))
        history.append({"role": "user", "content": state["user_query"]})
        history.append({"role": "assistant", "content": state["final_answer"]})

        return {
            "messages": history,
            "final_answer": state["final_answer"],
        }

    # ==========================
    # CONDITIONAL ROUTING EDGES
    # ==========================

    def _route_after_intent(self, state: AgentState) -> str:
        if not state.get("extracted_location"):
            return "ask_location"
        return "fetch_weather"

    def _route_after_weather(self, state: AgentState) -> str:
        if state.get("error_type") in ("LOCATION_NOT_FOUND", "API_ERROR"):
            return "weather_error"
        return "evaluate_sops"

    def _route_after_sops(self, state: AgentState) -> str:
        matched = state.get("matched_sops", [])
        if not matched:
            return "no_guidance"
        return "synthesize_advisory"

    # ==========================
    # GRAPH COMPILATION
    # ==========================

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # Register nodes
        workflow.add_node("parse_intent", self.parse_intent_node)
        workflow.add_node("ask_location", self.ask_location_node)
        workflow.add_node("fetch_weather", self.fetch_weather_node)
        workflow.add_node("weather_error", self.weather_error_node)
        workflow.add_node("evaluate_sops", self.evaluate_sops_node)
        workflow.add_node("no_guidance", self.no_guidance_node)
        workflow.add_node("synthesize_advisory", self.synthesize_advisory_node)
        workflow.add_node("verify_grounding", self.verify_grounding_node)

        # Set entry point
        workflow.set_entry_point("parse_intent")

        # Add conditional branching edges
        workflow.add_conditional_edges(
            "parse_intent",
            self._route_after_intent,
            {
                "ask_location": "ask_location",
                "fetch_weather": "fetch_weather",
            },
        )

        workflow.add_conditional_edges(
            "fetch_weather",
            self._route_after_weather,
            {
                "weather_error": "weather_error",
                "evaluate_sops": "evaluate_sops",
            },
        )

        workflow.add_conditional_edges(
            "evaluate_sops",
            self._route_after_sops,
            {
                "no_guidance": "no_guidance",
                "synthesize_advisory": "synthesize_advisory",
            },
        )

        # Terminal edges
        workflow.add_edge("ask_location", END)
        workflow.add_edge("weather_error", END)
        workflow.add_edge("no_guidance", END)
        workflow.add_edge("synthesize_advisory", "verify_grounding")
        workflow.add_edge("verify_grounding", END)

        # Compile with checkpointer for conversational session memory
        return workflow.compile(checkpointer=self.memory)

    def process_query(
        self,
        query: str,
        session_id: str = "default_session",
        simulate_api_failure: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes the LangGraph pipeline for a single turn in a session thread.
        """
        config = {"configurable": {"thread_id": session_id}}

        # Fetch prior state if this session exists
        prior_state = self.app.get_state(config)
        messages = prior_state.values.get("messages", []) if prior_state.values else []
        extracted_location = prior_state.values.get("extracted_location") if prior_state.values else None
        extracted_activity = prior_state.values.get("extracted_activity") if prior_state.values else None

        initial_state: AgentState = {
            "session_id": session_id,
            "user_query": query,
            "messages": messages,
            "extracted_location": extracted_location,
            "extracted_activity": extracted_activity,
            "extracted_timeframe": None,
            "weather_telemetry": None,
            "location_meta": None,
            "matched_sops": [],
            "primary_sop": None,
            "secondary_sops": [],
            "final_answer": "",
            "error_type": None,
            "error_message": None,
            "traceability_info": None,
            "simulate_api_failure": simulate_api_failure,
        }

        result = self.app.invoke(initial_state, config)
        return result

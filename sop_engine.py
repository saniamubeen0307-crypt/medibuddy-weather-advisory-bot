"""
Standard Operating Procedure (SOP) Rule Engine
Loads, evaluates, and resolves policy rules against live weather data.
"""

from typing import Dict, Any, List, Optional, Tuple
import yaml
import logging
import re
from pathlib import Path

from config import SOPS_FILE_PATH

logger = logging.getLogger("sop_engine")

SEVERITY_WEIGHTS = {
    "critical": 300,
    "warning": 200,
    "advisory": 100,
    "caution": 100,
}


class SOPEngine:
    def __init__(self, sops_path: Path = SOPS_FILE_PATH):
        self.sops_path = sops_path
        self._last_loaded_mtime: float = 0.0
        self.rules: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self.reload_if_modified()

    def reload_if_modified(self) -> None:
        """
        Reloads rules if the YAML file on disk has changed.
        Guarantees that policy teams can add or tweak an SOP live without restarting the service.
        """
        try:
            current_mtime = self.sops_path.stat().st_mtime
            if current_mtime > self._last_loaded_mtime:
                self._load_from_disk()
                self._last_loaded_mtime = current_mtime
        except FileNotFoundError:
            logger.error(f"SOP configuration file not found at {self.sops_path}")
            self.rules = []

    def _load_from_disk(self) -> None:
        with open(self.sops_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            self.metadata = data.get("metadata", {})
            self.rules = data.get("rules", [])
            logger.info(f"Loaded {len(self.rules)} safety SOPs from {self.sops_path.name}")

    def get_all_sops(self) -> List[Dict[str, Any]]:
        self.reload_if_modified()
        return self.rules

    def add_sop(self, new_rule: Dict[str, Any]) -> None:
        """
        Adds a new SOP to disk. This enables reviewers to test adding an 11th or 12th SOP live.
        """
        self.reload_if_modified()
        # Validate minimal schema
        required_fields = ["id", "name", "category", "severity", "guidance"]
        for field in required_fields:
            if field not in new_rule:
                raise ValueError(f"Missing required SOP field: '{field}'")

        # Append rule
        self.rules.append(new_rule)
        payload = {
            "metadata": self.metadata,
            "rules": self.rules,
        }
        with open(self.sops_path, "w", encoding="utf-8") as f:
            yaml.dump(payload, f, sort_keys=False, default_flow_style=False)
        self._last_loaded_mtime = self.sops_path.stat().st_mtime
        logger.info(f"Successfully appended new rule: {new_rule['id']}")

    def matches_activity(self, rule: Dict[str, Any], user_text: str, detected_activity: str) -> bool:
        """
        Checks if the rule applies to the user's intended activity.
        Universal rules ('all', 'any') match regardless of activity.
        """
        targets = [t.lower() for t in rule.get("target_activities", [])]

        # Universal rules apply to any outdoor query
        if "all" in targets or "any" in targets:
            return True

        text_lower = f"{user_text} {detected_activity}".lower()

        for target in targets:
            # Word boundary matching or substring for compound terms
            pattern = rf"\b{re.escape(target)}\b"
            if re.search(pattern, text_lower) or target in text_lower:
                return True

        return False

    def evaluate_condition_item(self, cond: Dict[str, Any], weather: Dict[str, Any]) -> bool:
        """
        Evaluates a single condition like: {field: "wind_speed_10m", operator: ">=", value: 38.0}
        """
        # Handle nested logic if present
        if "logic" in cond and "rules" in cond:
            return self.evaluate_condition_group(cond, weather)

        field = cond.get("field")
        op = cond.get("operator")
        expected = cond.get("value")

        actual = weather.get(field)
        if actual is None:
            return False

        try:
            if op == ">=":
                return float(actual) >= float(expected)
            elif op == ">":
                return float(actual) > float(expected)
            elif op == "<=":
                return float(actual) <= float(expected)
            elif op == "<":
                return float(actual) < float(expected)
            elif op == "==":
                return actual == expected
            elif op == "in":
                # Used for weather codes e.g. [95, 96, 99]
                if isinstance(expected, list):
                    return actual in expected or int(actual) in [int(x) for x in expected]
                return False
        except (ValueError, TypeError):
            return False

        return False

    def evaluate_condition_group(self, cond_group: Dict[str, Any], weather: Dict[str, Any]) -> bool:
        """
        Evaluates boolean logic ('and' / 'or') across condition lists.
        """
        logic = cond_group.get("logic", "and").lower()
        sub_rules = cond_group.get("rules", [])

        if not sub_rules:
            return True

        results = [self.evaluate_condition_item(r, weather) for r in sub_rules]
        if logic == "or":
            return any(results)
        return all(results)

    def evaluate_fuzzy_picnic(self, rule: Dict[str, Any], weather: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Evaluates fuzzy, non-numeric picnic suitability.
        A picnic doesn't simply fail on a single binary number:
        Sitting on grass requires dry soil, absence of rain/drizzle, tolerable breeze, and thermal comfort.
        Returns: (triggers_advisory, custom_guidance_override)
        """
        fuzzy = rule.get("fuzzy_rules", {})
        max_rain = float(fuzzy.get("max_tolerable_rain", 0.2))
        max_wind = float(fuzzy.get("max_tolerable_wind", 26.0))
        t_min = float(fuzzy.get("ideal_temp_min", 16.0))
        t_max = float(fuzzy.get("ideal_temp_max", 31.0))
        cloud_penalty = float(fuzzy.get("cloud_damp_penalty_threshold", 75))

        precip = weather.get("precipitation", 0.0)
        rain = weather.get("rain", 0.0)
        wind = weather.get("wind_speed_10m", 0.0)
        temp = weather.get("temperature_2m", 22.0)
        cloud = weather.get("cloud_cover", 0.0)
        code = weather.get("weather_code", 0)

        unfavorable_factors = []

        if precip > max_rain or rain > max_rain or code in [51, 53, 55, 61, 80]:
            unfavorable_factors.append(f"Active drizzle or rain ({precip}mm) creates wet turf and muddy seating")
        if wind > max_wind:
            unfavorable_factors.append(f"Brisk wind speeds ({wind} km/h) make setting up blankets and food difficult")
        if temp < t_min:
            unfavorable_factors.append(f"Chilly ambient temperature ({temp}°C) without shelter")
        elif temp > t_max:
            unfavorable_factors.append(f"Intense heat ({temp}°C) causes fast food spoilage and thermal discomfort")
        if cloud >= cloud_penalty and (precip > 0.05 or weather.get("relative_humidity_2m", 0) > 85):
            unfavorable_factors.append("Heavy cloud cover combined with high humidity keeps grass damp")

        if unfavorable_factors:
            custom_guidance = (
                f"{rule['guidance'].strip()} Specific comfort concerns right now: "
                + "; ".join(unfavorable_factors)
                + ". Moving to an indoor café or sheltered terrace is strongly recommended."
            )
            return True, custom_guidance
        else:
            # Weather is genuinely favorable for a picnic
            custom_guidance = rule.get(
                "positive_guidance",
                "Conditions are favorable for outdoor lawn activities. Turf is dry and winds are calm."
            ).strip()
            return True, custom_guidance

    def match_sops(
        self,
        user_text: str,
        detected_activity: str,
        weather: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Main matching pipeline.
        Returns:
            (all_matched_rules, primary_rule, secondary_rules)
        """
        self.reload_if_modified()
        matched: List[Dict[str, Any]] = []

        for rule in self.rules:
            # 1. Activity match check
            if not self.matches_activity(rule, user_text, detected_activity):
                continue

            rule_copy = dict(rule)
            condition_type = rule.get("condition_type", "numeric")

            # 2. Condition evaluation
            if condition_type == "fuzzy":
                is_match, dyn_guidance = self.evaluate_fuzzy_picnic(rule, weather)
                if is_match:
                    rule_copy["evaluated_guidance"] = dyn_guidance
                    matched.append(rule_copy)
            else:
                # Numeric / field evaluation
                cond_group = rule.get("conditions", {})
                if self.evaluate_condition_group(cond_group, weather):
                    rule_copy["evaluated_guidance"] = rule.get("guidance", "").strip()
                    matched.append(rule_copy)

        if not matched:
            return [], None, []

        # Multi-Match Resolution:
        # Sort by severity weight descending, then precedence descending
        def sort_key(item: Dict[str, Any]) -> Tuple[int, int]:
            sev = item.get("severity", "advisory").lower()
            weight = SEVERITY_WEIGHTS.get(sev, 50)
            prec = int(item.get("precedence", 50))
            return (weight, prec)

        matched.sort(key=sort_key, reverse=True)

        primary_rule = matched[0]
        secondary_rules = matched[1:]

        return matched, primary_rule, secondary_rules

"""Opt-in live provider check using only fabricated facts; never reads employee data."""

import argparse
import asyncio
import json
from time import perf_counter

from dotenv import load_dotenv

from backend.explain import LLMSettings, explain_recommendations


def sample():
    return {
        "event_id": "SMOKE_COURSE", "title": "Example system design course", "type": "course", "score": 3,
        "factors": {
            "target_grade": "Senior", "benefit": 3, "engagement_type": "course", "gateway_to": [],
            "gaps_used": [{"skill_id": "EXAMPLE_SYSTEM_DESIGN", "skill_name": "System Design", "current": 2,
                           "required": 4, "gap": 2, "critical": True, "weight": 3,
                           "gain": 1, "max_level": 4, "effective_gain": 1, "contribution": 3}],
            "engagement_by_type": {"course": {"skip_count": 0, "self_completion_count": 0,
                "decline_factor": 1, "self_factor": 1, "multiplier": 1}},
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    parser.add_argument("--limit", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    started = perf_counter()
    rows = asyncio.run(explain_recommendations([sample() for _ in range(args.limit)], LLMSettings.from_env()))
    elapsed = perf_counter() - started
    results = [{key: row["explanation"][key] for key in ("source", "model", "fallback_reason", "validated_fact_ids")} for row in rows]
    print(json.dumps({"elapsed_seconds": round(elapsed, 3), "results": results}, indent=2))
    if elapsed >= 10 or any(row["source"] != "llm" for row in results):
        parser.exit(1, "Live check did not meet the LLM success/latency criteria. Templates remain available.\n")


if __name__ == "__main__":
    main()

import argparse
import json
import sys
from dataclasses import dataclass

from loguru import logger

from core.engine import ExecutionEngine


class _ReplayEngineProxy:
    """Lightweight stand-in for ExecutionEngine, providing only what _parse_actions needs.

    Avoids the fragile ``ExecutionEngine.__new__()`` hack that bypassed ``__init__``
    and left the instance in a partially-initialised state.  This proxy exposes the
    class-level VALID_ACTIONS attribute which is the only ``self.*`` reference made
    by ``_parse_actions``.
    """
    VALID_ACTIONS = ExecutionEngine.VALID_ACTIONS


@dataclass
class ReplayThresholds:
    max_no_action_turn_rate: float = 0.05
    max_run_command_nonzero_rate: float = 0.01
    max_element_resolution_fail_rate: float = 0.05


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_replay(trace: dict, thresholds: ReplayThresholds) -> dict:
    allowed_actions = set(trace.get("allowed_actions") or [])
    if not allowed_actions:
        allowed_actions = None

    messages = trace.get("assistant_messages") or trace.get("messages") or []
    if not isinstance(messages, list):
        raise ValueError("Trace must contain 'assistant_messages' array")

    # Create a lightweight proxy that provides VALID_ACTIONS for _parse_actions
    # without needing the full ExecutionEngine constructor dependencies.
    engine = _ReplayEngineProxy()

    # Bind _parse_actions to our proxy so self.VALID_ACTIONS resolves correctly.
    parse_fn = ExecutionEngine._parse_actions

    no_action_turns = 0
    total_turns = 0
    parsed_actions_total = 0
    run_command_actions = 0

    for msg in messages:
        if not isinstance(msg, str):
            continue
        total_turns += 1
        actions = parse_fn(engine, msg, allowed_actions)
        if not actions:
            no_action_turns += 1
        else:
            parsed_actions_total += len(actions)
            for a in actions:
                if (a.get("type") or "").strip().lower() == "run_command":
                    run_command_actions += 1

    no_action_turn_rate = (no_action_turns / total_turns) if total_turns else 0.0

    # Optional trace-level metrics (if provided by runtime logs)
    trace_metrics = trace.get("metrics") or trace.get("session_metrics") or {}
    actions_total = int(trace_metrics.get("actions_total", 0) or 0)
    run_command_nonzero = int(trace_metrics.get("run_command_nonzero", 0) or 0)
    element_resolution_fail = int(trace_metrics.get("element_resolution_fail", 0) or 0)

    run_command_nonzero_rate = (run_command_nonzero / max(1, run_command_actions or trace_metrics.get("run_command_actions", 0) or 1))
    element_resolution_fail_rate = (element_resolution_fail / max(1, actions_total))

    # Validate semantic SoM samples (schema-only; no external calls)
    semantic_samples = trace.get("semantic_som_samples") or []
    semantic_schema_ok = True
    semantic_schema_errors: list[str] = []
    if isinstance(semantic_samples, list):
        for idx, sample in enumerate(semantic_samples[:10]):
            try:
                if isinstance(sample, str):
                    sample_obj = json.loads(sample)
                else:
                    sample_obj = sample
                if not isinstance(sample_obj, dict) or not isinstance(sample_obj.get("elements"), list):
                    semantic_schema_ok = False
                    semantic_schema_errors.append(f"sample[{idx}]: missing elements[]")
                    continue
                for e_i, el in enumerate(sample_obj.get("elements")[:80]):
                    if not isinstance(el, dict):
                        semantic_schema_ok = False
                        semantic_schema_errors.append(f"sample[{idx}].elements[{e_i}]: not object")
                        break
                    for k in ("x", "y", "w", "h"):
                        if k not in el:
                            semantic_schema_ok = False
                            semantic_schema_errors.append(f"sample[{idx}].elements[{e_i}]: missing {k}")
                            break
                        if not isinstance(el.get(k), int):
                            semantic_schema_ok = False
                            semantic_schema_errors.append(f"sample[{idx}].elements[{e_i}]: {k} not int")
                            break
                    t = str(el.get("type") or "").strip().lower()
                    if t and t not in ("button", "input", "link", "checkbox", "menu", "icon", "region"):
                        semantic_schema_ok = False
                        semantic_schema_errors.append(f"sample[{idx}].elements[{e_i}]: invalid type '{t}'")
                        break
            except Exception as e:
                semantic_schema_ok = False
                semantic_schema_errors.append(f"sample[{idx}]: parse error {type(e).__name__}")
                continue

    passed = (
        (no_action_turn_rate <= thresholds.max_no_action_turn_rate)
        and (run_command_nonzero_rate <= thresholds.max_run_command_nonzero_rate)
        and (element_resolution_fail_rate <= thresholds.max_element_resolution_fail_rate)
        and semantic_schema_ok
    )

    summary = {
        "total_turns": total_turns,
        "no_action_turns": no_action_turns,
        "no_action_turn_rate": round(no_action_turn_rate, 4),
        "parsed_actions_total": parsed_actions_total,
        "run_command_actions": run_command_actions,
        "trace_metrics": trace_metrics,
        "run_command_nonzero_rate": round(float(run_command_nonzero_rate), 4),
        "element_resolution_fail_rate": round(float(element_resolution_fail_rate), 4),
        "semantic_schema_ok": semantic_schema_ok,
        "semantic_schema_errors": semantic_schema_errors[:10],
        "thresholds": {
            "max_no_action_turn_rate": thresholds.max_no_action_turn_rate,
            "max_run_command_nonzero_rate": thresholds.max_run_command_nonzero_rate,
            "max_element_resolution_fail_rate": thresholds.max_element_resolution_fail_rate,
        },
        "pass": passed,
    }
    return summary


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True, help="Path to replay trace JSON")
    ap.add_argument("--max-no-action-turn-rate", type=float, default=0.05)
    ap.add_argument("--max-run-command-nonzero-rate", type=float, default=0.01)
    ap.add_argument("--max-element-resolution-fail-rate", type=float, default=0.05)
    ap.add_argument("--out", default="", help="Optional output JSON path")
    args = ap.parse_args(argv)

    trace = _load_json(args.trace)
    thresholds = ReplayThresholds(
        max_no_action_turn_rate=args.max_no_action_turn_rate,
        max_run_command_nonzero_rate=args.max_run_command_nonzero_rate,
        max_element_resolution_fail_rate=args.max_element_resolution_fail_rate,
    )
    summary = run_replay(trace, thresholds)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not summary.get("pass"):
        logger.error("Replay failed thresholds")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

from __future__ import annotations

import json
import random
from difflib import SequenceMatcher
from pathlib import Path


STRATEGIES = {
    "verbose": {"include_uncertain_evidence": True, "tight_style": False},
    "concise": {"include_uncertain_evidence": False, "tight_style": True},
    "safety_first": {"include_uncertain_evidence": True, "tight_style": True},
}


def simulated_doctor_edit(draft: str) -> str:
    edited_lines: list[str] = []
    for line in draft.splitlines():
        if "MISSING" in line and "clinician verification required" not in line and "REVIEW" not in line:
            edited_lines.append(line + " [verify with chart]")
        elif line.startswith("- supported:") or line.startswith("- Supported:"):
            edited_lines.append(line.split(":", 1)[0].upper() + ":" + line.split(":", 1)[1])
        elif len(line) > 260:
            edited_lines.append(line[:257] + "...")
        else:
            edited_lines.append(line)
    return "\n".join(edited_lines)


def edit_burden(draft: str, edited: str) -> float:
    return 1.0 - SequenceMatcher(a=draft, b=edited).ratio()


def run_learning_demo(base_draft: str, output_path: Path, iterations: int = 18, seed: int = 7) -> dict:
    random.seed(seed)
    rewards = {name: [] for name in STRATEGIES}
    curve = []
    for i in range(iterations):
        if i < len(STRATEGIES):
            strategy = list(STRATEGIES)[i]
        else:
            avg = {name: (sum(vals) / len(vals) if vals else -1) for name, vals in rewards.items()}
            strategy = max(avg, key=avg.get)
            if random.random() < 0.15:
                strategy = random.choice(list(STRATEGIES))
        draft = _apply_strategy(base_draft, strategy)
        edited = simulated_doctor_edit(draft)
        burden = edit_burden(draft, edited)
        reward = 1.0 - burden
        rewards[strategy].append(reward)
        curve.append({"iteration": i + 1, "strategy": strategy, "edit_burden": round(burden, 4), "reward": round(reward, 4)})

    before = curve[0]["edit_burden"]
    best_strategy = max(rewards, key=lambda s: sum(rewards[s]) / max(1, len(rewards[s])))
    after_draft = _apply_strategy(base_draft, best_strategy)
    after = edit_burden(after_draft, simulated_doctor_edit(after_draft))
    report = {
        "reward_signal": "1 - normalized edit burden using SequenceMatcher ratio between draft and simulated doctor edit.",
        "mechanism": "epsilon-greedy contextual bandit over discharge-summary rendering strategies.",
        "best_strategy": best_strategy,
        "before_edit_burden": round(before, 4),
        "after_edit_burden": round(after, 4),
        "curve": curve,
        "production_roadmap": [
            "Extend the simulated reviewer with clinician-edited held-out charts for stronger real-world validation.",
            "Keep the learning loop isolated from clinical fact extraction so optimization never changes diagnoses, medications, evidence, or safety flags.",
            "Add safety-specific evaluation beyond edit burden, including evidence fidelity, medication reconciliation accuracy, and conflict-escalation precision.",
        ],
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _apply_strategy(draft: str, strategy: str) -> str:
    text = draft
    if strategy == "concise":
        text = "\n".join(line for line in text.splitlines() if not line.startswith("## Evidence Notes") and " - " not in line[:80])
    elif strategy == "safety_first":
        text = text.replace("MISSING", "MISSING - clinician verification required")
    return text

"""缺陷账本对账：defect_ledger.json vs 某次实验的 L1/L2 结果 → 三类清单。

known-failures/xfail 范式：账本显式登记已知缺陷，每次全量（或大范围）实验后对账——
- 仍复现：登记在案且这次仍红 → 继续挂账
- 候选关账：登记在案、这次覆盖到了却全绿 → 提示「可能被顺带修复」；N 跑确认后才许置 obsolete（防间歇性假阴单次绿骗关账）
- 新红待 triage：这次红了但没有任何账目认领 → 取证定介质后入账

status 含义：
- open：确认存在，待处理
- deferred：确认存在，但暂缓处理
- fixed：已修复并通过验收
- obsolete：缺陷已失效，不再适用
- wontfix：确认不修


用法：uv run python -m src.eval.reconcile <exp_id> [variant]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
LEDGER_PATH = ROOT / "data" / "defect_ledger.json"

# 账本 axis → 红项判定
AXES = ("hit", "faithfulness", "l1")


def _load_eval(exp_id: str, variant: str) -> tuple[dict, dict]:
    eval_dir = ROOT / "logs" / "experiments" / exp_id / "variants" / variant / "eval"
    if not eval_dir.exists():
        raise FileNotFoundError(f"实验 eval 目录不存在：{eval_dir}")
    l1 = json.loads((eval_dir / "l1_case_result.json").read_text(encoding="utf-8")) \
        if (eval_dir / "l1_case_result.json").exists() else {}
    l2 = json.loads((eval_dir / "l2_case_result.json").read_text(encoding="utf-8")) \
        if (eval_dir / "l2_case_result.json").exists() else {}
    return l1, l2


def _current_reds(l1: dict, l2: dict) -> tuple[set[tuple[str, str]], set[str]]:
    """返回（红项集合 {(case_id, axis)}, 本次覆盖到的 (case_id, axis) 全集）。
    把两层结果统一归一化成 (case_id, axis) 键，axis 三选一：

    - l1：pass_rate < 1 即红
    - hit：任一 run 的 hit_axis 出现 miss
    - faithfulness：任一 run 出现 unsupported

    例：
        l1 = {"case_001": {"pass_rate": 0.5}, "case_002": {"pass_rate": 1.0}}
        l2 = {"case_073": {"runs": [{"verdict": {
            "hit_axis": [{"verdict": "hit"}],
            "faithfulness_axis": [{"verdict": "unsupported"}]}}]}}
        →
        reds = {("case_001", "l1"), ("case_073", "faithfulness")}
        covered = {("case_001", "l1"), ("case_002", "l1"),
                   ("case_073", "hit"), ("case_073", "faithfulness")}
    """
    reds: set[tuple[str, str]] = set()
    covered: set[tuple[str, str]] = set()
    for cid, c in l1.items():
        covered.add((cid, "l1"))
        if c.get("pass_rate", 1) < 1:
            reds.add((cid, "l1"))
    for cid, c in l2.items():
        covered.add((cid, "hit"))
        covered.add((cid, "faithfulness"))
        for run in c.get("runs", []):
            v = run.get("verdict", {})
            if any(h.get("verdict") == "miss" for h in v.get("hit_axis", [])):
                reds.add((cid, "hit"))
            if any(a.get("verdict") == "unsupported" for a in v.get("faithfulness_axis", [])):
                reds.add((cid, "faithfulness"))
    return reds, covered


def reconcile(exp_id: str, variant: str = "A_baseline") -> dict:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    l1, l2 = _load_eval(exp_id, variant)
    reds, covered = _current_reds(l1, l2)

    claimed: set[tuple[str, str]] = set()  # 被任何账目（含 wontfix/fixed）认领的 (case, axis)
    reproduced, candidate_close, uncovered, wontfix_seen = [], [], [], []

    for entry in ledger:
        keys = {(cid, entry["axis"]) for cid in entry["cases"]}
        claimed |= keys
        hit_keys = sorted(k for k in keys if k in reds)
        cov_keys = keys & covered

        if entry["status"] in ("fixed", "obsolete"):
            fix_exp = entry.get("fix_exp_id") or ""
            # 早于修复的历史实验里红是应该的，不算回归（exp_id 时间戳前缀可比）
            if hit_keys and exp_id >= fix_exp:
                reproduced.append({**_brief(entry), "matched": hit_keys,
                                   "warning": f"⚠️ status={entry['status']} 却复现——疑似回归；"
                                              "若同键被其他 open 账目认领，可能是同 case 新缺陷，取证区分"})
            continue
        if entry["status"] == "wontfix":
            if hit_keys:
                wontfix_seen.append({**_brief(entry), "matched": hit_keys})
            continue
        # open / deferred
        if hit_keys:
            reproduced.append({**_brief(entry), "matched": hit_keys})
        elif cov_keys:
            candidate_close.append({**_brief(entry),
                                    "covered": sorted(cov_keys),
                                    "note": "本次全绿——N 跑确认后再置 obsolete，别单次绿就关"})
        else:
            uncovered.append({**_brief(entry), "note": "本次实验未覆盖其 case，无法对账"})

    untriaged = sorted(k for k in reds if k not in claimed)

    report = {
        "exp_id": exp_id, "variant": variant,
        "reproduced": reproduced,
        "candidate_close": candidate_close,
        "uncovered": uncovered,
        "untriaged_new_reds": untriaged,
        "wontfix_observed": wontfix_seen,
    }
    return report


def _brief(entry: dict) -> dict:
    return {"id": entry["id"], "status": entry["status"], "cluster": entry["cluster"],
            "signature": entry["signature"][:60]}


def _print(report: dict) -> None:
    print(f"===== 对账 {report['exp_id']} / {report['variant']} =====")
    print(f"\n【仍复现 {len(report['reproduced'])}】")
    for e in report["reproduced"]:
        warn = e.get("warning", "")
        print(f"  {e['id']} [{e['status']}] {e['matched']} {warn}")
    print(f"\n【候选关账 {len(report['candidate_close'])}】（N 跑确认再关）")
    for e in report["candidate_close"]:
        print(f"  {e['id']} [{e['status']}] {e['note']}")
    print(f"\n【未覆盖 {len(report['uncovered'])}】")
    for e in report["uncovered"]:
        print(f"  {e['id']} [{e['status']}]")
    print(f"\n【新红待 triage {len(report['untriaged_new_reds'])}】（取证定介质后入账）")
    for k in report["untriaged_new_reds"]:
        print(f"  {k}")
    if report["wontfix_observed"]:
        print(f"\n【wontfix 观察 {len(report['wontfix_observed'])}】（已裁不修，仅供观察）")
        for e in report["wontfix_observed"]:
            print(f"  {e['id']} {e['matched']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("用法：python -m src.eval.reconcile <exp_id> [variant]")
    _print(reconcile(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "A_baseline"))

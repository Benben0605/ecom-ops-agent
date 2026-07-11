"""l2_fixtures_judge 轨落盘产物的唯一 schema 来源。

三方共用同一份定义，谁也别自己算一遍：
- src/eval/l2/fixtures.py     按它构造
- src/experiment/runner.py    按它落盘
- src/dashboard/experiment_adapter.py  按它读回

层级：FixturesCaseResult → CaseRecord → AnchorRecord → AnchorRun。
每层的"通过率"是不同的东西，所以名字也不同，别再靠上下文猜：
- AnchorRun.ok          这一条锚点在这一次 run 里符不符合预期
- AnchorRecord.ok_run_rate   这一条锚点 N 次 run 里 ok 的比例
- CaseRecord.run_pass_rate   这个 case 的 N 次 run 里「所有锚点同时 ok」的比例

改字段后必须跑 `uv run python -m src.contracts.export_schemas` 更新 docs/schemas/ 快照。
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, computed_field, model_validator

SCHEMA_VERSION = 1

Expect = Literal["supported", "unsupported"]
RunVerdict = Literal["supported", "unsupported", "not_extracted"]
AnchorFlag = Literal["pass", "false_positive", "false_negative"]


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _run_ok(expect: Expect, run_verdict: RunVerdict) -> bool:
    """唯一一处「这次 run 算不算符合预期」的判定。红锚要被抓住，绿锚不能被误伤。"""
    if expect == "unsupported":
        return run_verdict == "unsupported"
    return run_verdict != "unsupported"


def _verdict_of(matched: list["Assertion"]) -> RunVerdict:
    """唯一一处「这次 run 里该锚点的裁定」。三态：judge 没抽出匹配的断言 ≠ 判它 supported。"""
    if not matched:
        return "not_extracted"
    if any(a.verdict == "unsupported" for a in matched):
        return "unsupported"
    return "supported"


# ========== 叶子 ==========
class Assertion(BaseModel):
    """judge 忠实轴的一条断言。"""
    assertion: str
    verdict: Literal["supported", "unsupported"]
    evidence: str = ""


class HitPoint(BaseModel):
    """judge 命中轴的一个 golden point。"""
    point: str
    verdict: Literal["hit", "miss"]
    evidence: str = ""


class AnchorRun(BaseModel):
    """一条锚点在第 run_index 次 judge 里的结局。

    run_verdict 三态：judge 没抽出匹配的断言（not_extracted）≠ 判它 supported。
    绿锚从未被抽到也记 ok，靠 extract_rate 把这种低置信度的假绿暴露出来。
    """
    run_index: int  # 1-based
    ok: bool
    matched: list[Assertion]

    @classmethod
    def build(cls, *, run_index: int, matched: list[Assertion], expect: Expect) -> AnchorRun:
        return cls(run_index=run_index, ok=_run_ok(expect, _verdict_of(matched)), matched=matched)

    @computed_field
    @property
    def run_verdict(self) -> RunVerdict:
        return _verdict_of(self.matched)


class JudgeVerdict(BaseModel):
    """某次 run 的 judge 原始输出，未按锚点切分。下钻时用来看 judge 到底抽了什么。"""
    run_index: int
    hit_axis: list[HitPoint] = []
    faithfulness_axis: list[Assertion] = []


class FixtureInput(BaseModel):
    """夹具冻结的 judge 输入，原样复制进产物，下钻时不必回查夹具文件。"""
    question: str
    answer: str
    tool_outputs: list[str]
    golden_points: list[str]


# ========== 锚点 ==========
class AnchorRecord(BaseModel):
    """一条锚点 N 次 run 的汇总。计数和 flag 全部由 runs 派生，不可能与 runs 分叉。"""
    anchor_id: str
    case_id: str
    axis: Literal["faithfulness"]
    match: str
    expect: Expect
    note: str
    runs: list[AnchorRun]

    @model_validator(mode="after")
    def _runs_ok_matches_expect(self) -> AnchorRecord:
        for run in self.runs:
            if run.ok != _run_ok(self.expect, run.run_verdict):
                raise ValueError(
                    f"[{self.anchor_id}] run#{run.run_index} 的 ok={run.ok} 与 "
                    f"expect={self.expect}/run_verdict={run.run_verdict} 不自洽"
                )
        return self

    @computed_field
    @property
    def n(self) -> int:
        return len(self.runs)

    @computed_field
    @property
    def unsupported_runs(self) -> int:
        return sum(1 for r in self.runs if r.run_verdict == "unsupported")

    @computed_field
    @property
    def supported_runs(self) -> int:
        return sum(1 for r in self.runs if r.run_verdict == "supported")

    @computed_field
    @property
    def not_extracted_runs(self) -> int:
        return sum(1 for r in self.runs if r.run_verdict == "not_extracted")

    @computed_field
    @property
    def ok_run_rate(self) -> float | None:
        return _rate(sum(1 for r in self.runs if r.ok), self.n)

    @computed_field
    @property
    def flag(self) -> AnchorFlag:
        """红锚必须次次抓住，漏一次即假阴；绿锚一次都不能误伤，错一次即假阳。"""
        if all(r.ok for r in self.runs):
            return "pass"
        return "false_negative" if self.expect == "unsupported" else "false_positive"

    @property
    def is_red(self) -> bool:
        return self.expect == "unsupported"


class FailedAnchor(BaseModel):
    """metrics 里的失败锚点索引；完整下钻回 case_result 按 anchor_id 找。"""
    case_id: str
    anchor_id: str
    match: str
    expect: Expect
    flag: AnchorFlag


# ========== case ==========
class CaseRecord(BaseModel):
    case_id: str
    bucket: str
    input: FixtureInput
    anchors: list[AnchorRecord]
    judge_verdicts: list[JudgeVerdict]

    @model_validator(mode="after")
    def _every_anchor_covers_every_run(self) -> CaseRecord:
        n = len(self.judge_verdicts)
        for anchor in self.anchors:
            if anchor.n != n:
                raise ValueError(
                    f"[{self.case_id}] 锚点 {anchor.anchor_id} 有 {anchor.n} 条 run，"
                    f"但本 case 跑了 {n} 次 judge"
                )
        return self

    @computed_field
    @property
    def n(self) -> int:
        return len(self.judge_verdicts)

    @computed_field
    @property
    def run_pass_rate(self) -> float | None:
        """N 次 run 里「所有锚点同时 ok」的比例。与 l1/l2 轨的 pass_rate 同义，可横向比。"""
        if not self.anchors:
            return None
        passing = sum(1 for i in range(self.n) if all(a.runs[i].ok for a in self.anchors))
        return _rate(passing, self.n)

    @computed_field
    @property
    def anchor_count(self) -> int:
        return len(self.anchors)

    @computed_field
    @property
    def passed_anchor_count(self) -> int:
        return sum(1 for a in self.anchors if a.flag == "pass")

    @computed_field
    @property
    def anchor_pass_rate(self) -> float | None:
        return _rate(self.passed_anchor_count, self.anchor_count)

    @computed_field
    @property
    def has_issue(self) -> bool:
        return self.passed_anchor_count < self.anchor_count

    @computed_field
    @property
    def issue_types(self) -> list[AnchorFlag]:
        return sorted({a.flag for a in self.anchors if a.flag != "pass"})


# ========== 落盘产物 ==========
class FixturesCaseResult(BaseModel):
    """下钻详情。artifact: l2_fixtures_case_result.json"""
    schema_version: Literal[1] = SCHEMA_VERSION
    artifact: Literal["l2_fixtures_case_result"] = "l2_fixtures_case_result"
    cases: dict[str, CaseRecord]


class FixturesMetrics(BaseModel):
    """headline。artifact: l2_fixtures_metrics.json

    只存计数，率一律 computed——这样看到 extract_rate=0.25 时，分子分母就在旁边。
    唯一构造入口是 from_cases()，dashboard 的分桶拆解也调它，不许另写一份。
    """
    schema_version: Literal[1] = SCHEMA_VERSION
    artifact: Literal["l2_fixtures_metrics"] = "l2_fixtures_metrics"
    derived_from: Literal["l2_fixtures_case_result.json"] = "l2_fixtures_case_result.json"

    n: int
    case_count: int
    issue_case_count: int
    anchor_count: int
    passed_anchor_count: int
    red_anchor_count: int
    green_anchor_count: int
    anchor_runs: int
    not_extracted_runs: int
    red_runs: int
    red_unsupported_runs: int
    green_runs: int
    green_unsupported_runs: int
    failed_anchors: list[FailedAnchor]

    @classmethod
    def from_cases(cls, cases: Iterable[CaseRecord]) -> FixturesMetrics:
        cases = list(cases)
        anchors = [a for c in cases for a in c.anchors]
        red = [a for a in anchors if a.is_red]
        green = [a for a in anchors if not a.is_red]
        return cls(
            n=max((c.n for c in cases), default=0),
            case_count=len(cases),
            issue_case_count=sum(1 for c in cases if c.has_issue),
            anchor_count=len(anchors),
            passed_anchor_count=sum(1 for a in anchors if a.flag == "pass"),
            red_anchor_count=len(red),
            green_anchor_count=len(green),
            anchor_runs=sum(a.n for a in anchors),
            not_extracted_runs=sum(a.not_extracted_runs for a in anchors),
            red_runs=sum(a.n for a in red),
            red_unsupported_runs=sum(a.unsupported_runs for a in red),
            green_runs=sum(a.n for a in green),
            green_unsupported_runs=sum(a.unsupported_runs for a in green),
            failed_anchors=[
                FailedAnchor(case_id=a.case_id, anchor_id=a.anchor_id, match=a.match,
                             expect=a.expect, flag=a.flag)
                for a in anchors if a.flag != "pass"
            ],
        )

    @computed_field
    @property
    def failed_anchor_count(self) -> int:
        return len(self.failed_anchors)

    @computed_field
    @property
    def anchor_pass_rate(self) -> float | None:
        return _rate(self.passed_anchor_count, self.anchor_count)

    @computed_field
    @property
    def red_anchor_recall(self) -> float | None:
        """红锚该被判 unsupported = 越界被抓住。分母是 红锚数 × n。"""
        return _rate(self.red_unsupported_runs, self.red_runs)

    @computed_field
    @property
    def green_anchor_fp_rate(self) -> float | None:
        """绿锚被判 unsupported = 误伤。与 red_anchor_recall 同一个分子形状，两种含义。"""
        return _rate(self.green_unsupported_runs, self.green_runs)

    @computed_field
    @property
    def extract_rate(self) -> float | None:
        """抽取覆盖度：绿锚从未被抽到也记 pass，靠这个把低置信度的假绿暴露出来。"""
        if not self.anchor_runs:
            return None
        return 1 - self.not_extracted_runs / self.anchor_runs


ARTIFACTS: dict[str, type[BaseModel]] = {
    "l2_fixtures_case_result": FixturesCaseResult,
    "l2_fixtures_metrics": FixturesMetrics,
}

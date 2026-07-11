"""把 src/contracts/ 下的 model 导出成 schemas/*.schema.json 快照。

快照与契约同处一目录（src/contracts/schemas/），必然入库——docs/ 是 gitignore 的私有笔记，
放那儿快照进不了 diff，机制就废了。改契约后跑一次，快照进 PR diff——变更在 review 里看得见。
tests/test_contract_schemas.py 会钉住快照与 model 一致。

    uv run python -m src.contracts.export_schemas
"""
import json
from pathlib import Path

from pydantic import BaseModel

from src.contracts.l2_fixtures import ARTIFACTS as L2_FIXTURES_ARTIFACTS

ROOT = Path(__file__).parents[2]
SCHEMA_DIR = Path(__file__).parent / "schemas"

ARTIFACTS: dict[str, type[BaseModel]] = {**L2_FIXTURES_ARTIFACTS}


def schema_of(model: type[BaseModel]) -> str:
    # serialization 模式：schema 描述的是磁盘上的产物，computed_field 必须在里面
    # （默认的 validation 模式会把它们全部漏掉）
    schema = model.model_json_schema(mode="serialization")
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def export() -> list[Path]:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in ARTIFACTS.items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        path.write_text(schema_of(model), encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for path in export():
        print(f"写入 {path.relative_to(ROOT)}")

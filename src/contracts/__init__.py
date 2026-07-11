"""跨边界数据契约。规则见 CONTRIBUTING.md「跨边界数据契约」。"""
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)


def load_artifact(path: Path, model: type[M]) -> M:
    """按契约读回落盘产物。

    schema 不匹配时报错报到底——旧产物就该重跑或删除。这里不做兼容层：
    悄悄吞掉一个版本的差异，就是把今天的错乱感原样留给三个月后的自己。
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        return model.model_validate(raw)
    except ValidationError as e:
        found = raw.get("schema_version") if isinstance(raw, dict) else None
        expected = model.model_fields["schema_version"].default
        raise ValueError(
            f"{path} 不符合 {model.__name__} 契约"
            f"（产物 schema_version={found}，当前契约 ={expected}）。\n"
            f"旧格式产物请重跑实验或删除该目录，不要加兼容层。\n原始错误：{e}"
        ) from e

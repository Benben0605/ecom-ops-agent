"""钉住 docs/schemas/*.schema.json 与 src/contracts/ 下的 model 一致。

改了契约却没跑 export_schemas → 这里红。schema 变更从此必须出现在 PR diff 里。
"""
import unittest

from src.contracts.export_schemas import ARTIFACTS, SCHEMA_DIR, schema_of


class ContractSchemaSnapshotTest(unittest.TestCase):
    def test_snapshots_match_models(self):
        for name, model in ARTIFACTS.items():
            with self.subTest(artifact=name):
                path = SCHEMA_DIR / f"{name}.schema.json"
                self.assertTrue(path.exists(), f"缺少 schema 快照：{path}")
                self.assertEqual(
                    path.read_text(encoding="utf-8"),
                    schema_of(model),
                    f"{name} 的 schema 快照过期——跑 "
                    f"`uv run python -m src.contracts.export_schemas` 并把 diff 一起提交",
                )

    def test_snapshot_dir_has_no_orphans(self):
        expected = {f"{name}.schema.json" for name in ARTIFACTS}
        actual = {p.name for p in SCHEMA_DIR.glob("*.schema.json")}
        self.assertEqual(actual - expected, set(), "docs/schemas/ 下有已删除 model 的残留快照")


if __name__ == "__main__":
    unittest.main()

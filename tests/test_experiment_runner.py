import unittest
from unittest.mock import patch

from src.experiment import runner


class ConfigSummaryTest(unittest.TestCase):
    def test_baseline_records_resolved_default_model(self):
        with patch.object(runner.config, "MODEL", "default-model"):
            self.assertEqual(
                runner._config_summary({}),
                {"model": "default-model"},
            )

    def test_explicit_model_is_preserved_with_other_config(self):
        self.assertEqual(
            runner._config_summary(
                {
                    "model": "candidate-model",
                    "tool_impls": {"query_order": object()},
                }
            ),
            {
                "model": "candidate-model",
                "tool_impls": ["query_order"],
            },
        )


if __name__ == "__main__":
    unittest.main()

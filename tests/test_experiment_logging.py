import json
import os
import sys
import tempfile
import types
import unittest

_fake_virtual_mem = types.SimpleNamespace(
    total=0,
    available=0,
    percent=0,
    used=0,
)

sys.modules.setdefault(
    "psutil",
    types.SimpleNamespace(
        cpu_percent=lambda interval=1: 0.0,
        virtual_memory=lambda: _fake_virtual_mem,
    ),
)

from scripts.experiments.experiment import Experiment, ExperimentConfig


class _DummyExperiment(Experiment):
    def on_start(self):
        self.logger.info("on_start invoked")

    def experiment_main(self):
        self.logger.info("experiment_main invoked")

    def on_end(self):
        self.logger.info("on_end invoked")


class ExperimentLoggingTests(unittest.TestCase):
    def test_main_process_logging_writes_to_file(self):
        Experiment._logging_configured = False

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            cfg = ExperimentConfig(
                name="dummy",
                data_dir=tmpdir,
                result_dir=tmpdir,
                log_dir=log_dir,
                experiment_dir=tmpdir,
            )
            cfg.K = 1
            cfg.category = "test"

            experiment = _DummyExperiment(cfg)
            experiment.metadata_path = os.path.join(tmpdir, "metadata.json")
            with open(experiment.metadata_path, "w", encoding="utf-8") as metadata_file:
                json.dump({}, metadata_file)

            experiment.run()
            experiment.end()

            log_path = os.path.join(log_dir, "main.log")
            self.assertTrue(os.path.exists(log_path), "main.log should exist")
            with open(log_path, encoding="utf-8") as log_file:
                content = log_file.read()

            self.assertIn("Experiment dummy started", content)
            self.assertIn("on_start invoked", content)
            self.assertIn("experiment_main invoked", content)
            self.assertIn("Experiment dummy ended", content)


if __name__ == "__main__":
    unittest.main()

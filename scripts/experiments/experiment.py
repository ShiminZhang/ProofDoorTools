import argparse
from abc import ABC, abstractmethod
import logging
import os
import platform
import json
import psutil


def get_machine_info():
    cpu_percent = psutil.cpu_percent(interval=1)
    virtual_mem = psutil.virtual_memory()
    system_info = {
        "system": platform.system(),
        "node": platform.node(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }
    machine_info = {
        "cpu_percent": cpu_percent,
        "memory_total": virtual_mem.total,
        "memory_available": virtual_mem.available,
        "memory_percent": virtual_mem.percent,
        "memory_used": virtual_mem.used,
        "system_info": system_info,
    }
    return machine_info

class ExperimentConfig:
    def __init__(
        self,
        name,
        data_dir,
        result_dir,
        log_dir,
        experiment_dir=None,
    ):
        self.name = name
        self.data_dir = data_dir
        self.result_dir = result_dir
        self.log_dir = log_dir
        self.experiment_dir = experiment_dir


class Experiment(ABC):
    _logging_configured = False

    def __init__(self, config: ExperimentConfig):
        self.metadata_path = "./experiment_metadatas.json"
        self.name = config.name
        self.config = config
        self._configure_logging()
        self._logger_name = f"proofdoor.main.{self.name}"
        logger = logging.getLogger(self._logger_name)
        logger.setLevel(logging.INFO)
        self.metadata = {
            "name": config.name,
            "data_dir": config.data_dir,
            "result_dir": config.result_dir,
            "log_dir": config.log_dir,
            "K": config.K,
            "category": config.category,
            "experiment_dir": config.experiment_dir,
        }

    @property
    def logger(self):
        return logging.getLogger(self._logger_name)

    def _configure_logging(self):
        if Experiment._logging_configured:
            return

        os.makedirs(self.config.log_dir, exist_ok=True)
        log_path = os.path.join(self.config.log_dir, f"main.log")
        if os.path.exists(log_path):
            os.remove(log_path)

        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [pid %(process)d] %(levelname)s: %(message)s"
            )
        )

        logger = logging.getLogger("proofdoor")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            logger.addHandler(handler)
        logger.propagate = False

        Experiment._logging_configured = True

    @abstractmethod
    def experiment_main(self):
        pass

    @abstractmethod
    def on_start(self):
        pass

    @abstractmethod
    def on_end(self):
        pass

    def end(self):
        self.on_end()
        self.logger.info("Experiment %s ended", self.name)

    def run(self):
        self.logger.info("Experiment %s started", self.name)
        metadata = {}
        if os.path.exists(self.metadata_path):
            with open(self.metadata_path, "r", encoding="utf-8") as existing:
                try:
                    metadata = json.load(existing)
                except json.JSONDecodeError:
                    metadata = {}
        metadata[self.name] = self.metadata
        with open(self.metadata_path, "w", encoding="utf-8") as updated:
            json.dump(metadata, updated, indent=4)
        self.logger.info("Experiment config: %s", self.config)
        # log machine info
        machine_info = get_machine_info()
        self.logger.info("Machine info: %s", machine_info)
        self.on_start()
        self.experiment_main()
        return

    pass

def main():
    pass

if __name__ == "__main__":
    main()

from os import path
from toml import load
from typing import Any

from .exception import ConfigException

DATA_DIR = "./data/"
CONFIG_FILE_NAME = "config.toml"

CONFIG_FILE = path.abspath(path.join(DATA_DIR, CONFIG_FILE_NAME))

class TOMLConfig:
    __slots__ = ("data", )

    def __init__(self, json_data: dict):
        self.data = json_data

    @classmethod
    def from_filename(cls, file_path: str):
        with open(file_path, "r", encoding="utf-8") as config_file:
            data = load(config_file)

        return cls(data)

    def get_table(self, name: str, ignore_empty: bool = False) -> "TOMLConfig":
        data = self.data.get(name)

        if data is None and not ignore_empty:
            raise ConfigException(f"Configuration table missing: '{name}'")

        return TOMLConfig(data)

    def get(self, name: str, fallback: Any = None, ignore_empty: bool = False) -> Any:
        data = self.data.get(name)

        if data is None and not ignore_empty:
            raise ConfigException(f"Configuration value missing: '{name}'")

        if data is None:
            return fallback
        else:
            return data


class AnalysisConfig:
    __slots__ = (
        "_config", "_table_paths",
        "SCROBBLES_JSON_PATH", "MUSIC_LIBRARY_ROOT"
    )

    def __init__(self, config_dict: TOMLConfig):
        self._config = config_dict

        self._table_paths = self._config.get_table("Paths")

        ##########
        # Paths
        ##########
        SCROBBLES_JSON = self._table_paths.get("scrobbles_json_path").format(
            DATA_DIR=DATA_DIR
        )
        self.SCROBBLES_JSON_PATH = path.abspath(SCROBBLES_JSON)
        self.MUSIC_LIBRARY_ROOT = path.abspath(self._table_paths.get("music_library_root"))


raw_config = TOMLConfig.from_filename(CONFIG_FILE)
config = AnalysisConfig(raw_config)

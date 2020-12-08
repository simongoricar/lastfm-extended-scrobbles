import logging
from os import path, mkdir
from toml import load
from typing import Any

from .exception import ConfigException

log = logging.getLogger(__name__)

DATA_DIR = "./data/"
CONFIG_FILE_NAME = "config.toml"
PYPROJECT_FILE_NAME = "pyproject.toml"

PYPROJECT_FILE = path.abspath(PYPROJECT_FILE_NAME)
CONFIG_FILE = path.abspath(path.join(DATA_DIR, CONFIG_FILE_NAME))

logging_name_to_level = {
    # Adapted from __init__.py of logging library, L108
    "critical": logging.CRITICAL,
    "fatal": logging.FATAL,
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
    "notset": logging.NOTSET,
}


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
        "_config",
        "_table_authentication", "_table_source_paths", "_table_dest_paths",
        "_table_cache", "_table_logging", "_table_fuzzy", "_table_genres",
        "LASTFM_API_KEY", "LASTFM_API_SECRET",
        "SCROBBLES_JSON_PATH", "MUSIC_LIBRARY_ROOT",
        "XLSX_OUTPUT_PATH",
        "CACHE_DIR", "LIBRARY_CACHE_FILE",
        "VERBOSITY", "CACHE_LOG_INTERVAL", "PARSE_LOG_INTERVAL",
        "FUZZY_MIN_TITLE", "FUZZY_MIN_ALBUM", "FUZZY_MIN_ARTIST", "FUZZY_YOUTUBE_MIN_TITLE",
        "MIN_GENRE_WEIGHT", "GENRES_USE_SPECIFIC", "MAX_GENRE_COUNT", "MIN_LASTFM_SIMILARITY"
    )

    def __init__(self, config_dict: TOMLConfig):
        self._config = config_dict

        self._table_authentication = self._config.get_table("Authentication")
        self._table_source_paths = self._config.get_table("SourcePaths")
        self._table_dest_paths = self._config.get_table("DestinationPaths")
        self._table_cache = self._config.get_table("Cache")
        self._table_logging = self._config.get_table("Logging")
        self._table_fuzzy = self._config.get_table("FuzzyMatching")
        self._table_genres = self._config.get_table("Genres")

        ##########
        # Authentication
        ##########
        self.LASTFM_API_KEY = self._table_authentication.get("lastfm_api_key")
        self.LASTFM_API_SECRET = self._table_authentication.get("lastfm_api_secret")

        ##########
        # SourcePaths
        ##########
        SCROBBLES_JSON = self._table_source_paths.get("scrobbles_json_path").format(
            DATA_DIR=DATA_DIR
        )
        self.SCROBBLES_JSON_PATH = path.abspath(SCROBBLES_JSON)
        self.MUSIC_LIBRARY_ROOT = path.abspath(self._table_source_paths.get("music_library_root"))

        ##########
        # DestinationPaths
        ##########
        XLSX_OUTPUT_PATH = path.abspath(self._table_dest_paths.get("xlsx_ouput_path").format(
            DATA_DIR=DATA_DIR
        ))
        self.XLSX_OUTPUT_PATH = XLSX_OUTPUT_PATH

        ##########
        # Cache
        ##########
        self.CACHE_DIR = path.abspath(self._table_cache.get("cache_dir").format(
            DATA_DIR=DATA_DIR
        ))
        if not path.isdir(self.CACHE_DIR):
            log.info(f"Creating cache directory: '{self.CACHE_DIR}'")
            mkdir(self.CACHE_DIR)

        self.LIBRARY_CACHE_FILE = path.abspath(self._table_cache.get("library_cache_file").format(
            DATA_DIR=DATA_DIR,
            CACHE_DIR=self.CACHE_DIR
        ))

        ##########
        # Logging
        ##########
        verbosity = self._table_logging.get("verbosity", "").lower()
        self.VERBOSITY = logging_name_to_level.get(verbosity)
        if self.VERBOSITY is None:
            log.warning("verbosity was not set properly, falling back to \"info\"")
            self.VERBOSITY = logging.INFO

        self.CACHE_LOG_INTERVAL = int(self._table_logging.get("cache_log_interval"))
        self.PARSE_LOG_INTERVAL = int(self._table_logging.get("parse_log_interval"))

        ##########
        # FuzzyMacthing
        ##########
        self.FUZZY_MIN_TITLE = int(self._table_fuzzy.get("local_library_title_min_match"))
        self.FUZZY_MIN_ALBUM = int(self._table_fuzzy.get("local_library_album_min_match"))
        self.FUZZY_MIN_ARTIST = int(self._table_fuzzy.get("local_library_artist_min_match"))
        self.FUZZY_YOUTUBE_MIN_TITLE = int(self._table_fuzzy.get("youtube_title_min_match"))

        ##########
        # Genres
        ##########
        self.MIN_GENRE_WEIGHT = int(self._table_genres.get("min_genre_weight"))
        # self.GENRES_USE_SPECIFIC = self._table_genres.get("use_most_specific")
        self.MAX_GENRE_COUNT = int(self._table_genres.get("max_genre_count"))
        self.MIN_LASTFM_SIMILARITY = int(self._table_genres.get("min_lastfm_suggestion_similarity"))




raw_config = TOMLConfig.from_filename(CONFIG_FILE)
config = AnalysisConfig(raw_config)

pyproject_config = TOMLConfig.from_filename(PYPROJECT_FILE)

pyproject_tool_poetry = pyproject_config.get_table("tool").get_table("poetry")

PROJECT_NAME = pyproject_tool_poetry.get("name")
VERSION = pyproject_tool_poetry.get("version")
REPOSITORY = pyproject_tool_poetry.get("repository")

import logging
from os import path, mkdir
from toml import load
from typing import Any, Optional

from .exception import ConfigException

log = logging.getLogger(__name__)

BASE_DIR = path.abspath(path.join(path.dirname(__file__), ".."))
DATA_DIR = path.abspath(path.join(BASE_DIR, "./data/"))
CONFIG_FILE_NAME = "config.toml"
PYPROJECT_FILE_NAME = "pyproject.toml"

PYPROJECT_FILE = path.abspath(path.join(BASE_DIR, PYPROJECT_FILE_NAME))
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
    """
    General-purpose toml config class.
    """
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
    """
    Parses and contains all the supported configuration values.
    """
    __slots__ = (
        "_config",
        "_table_authentication", "_table_source_paths", "_table_dest_paths",
        "_table_cache", "_table_logging", "_table_fuzzy", "_table_genres",
        # Authentication
        "LASTFM_API_KEY", "LASTFM_API_SECRET",
        # SourcePaths
        "SCROBBLES_JSON_PATH", "MUSIC_LIBRARY_ROOT",
        # DestinationPaths
        "XLSX_OUTPUT_PATH",
        # Cache
        "CACHE_DIR", "LIBRARY_CACHE_FILE",
        # Logging
        "VERBOSITY", "CACHE_LOG_INTERVAL", "PARSE_LOG_INTERVAL",
        # FuzzyMatching
        "FUZZY_MIN_TITLE", "FUZZY_MIN_ALBUM", "FUZZY_MIN_ARTIST", "FUZZY_YOUTUBE_MIN_TITLE",
        # Genres
        "MIN_TAG_WEIGHT", "GENRES_USE_SPECIFIC", "MAX_GENRE_COUNT", "MIN_LASTFM_SIMILARITY",
        "MAX_LASTFM_PAGES"
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
        self.LASTFM_API_KEY: str = self._table_authentication.get("lastfm_api_key")
        self.LASTFM_API_SECRET: str = self._table_authentication.get("lastfm_api_secret")

        ##########
        # SourcePaths
        ##########
        SCROBBLES_JSON: str = self._table_source_paths.get("scrobbles_json_path").format(
            DATA_DIR=DATA_DIR
        )
        self.SCROBBLES_JSON_PATH: str = path.abspath(SCROBBLES_JSON)
        self.MUSIC_LIBRARY_ROOT: str = path.abspath(self._table_source_paths.get("music_library_root"))

        ##########
        # DestinationPaths
        ##########
        XLSX_OUTPUT_PATH: str = path.abspath(self._table_dest_paths.get("xlsx_ouput_path").format(
            DATA_DIR=DATA_DIR
        ))
        self.XLSX_OUTPUT_PATH: str = XLSX_OUTPUT_PATH

        ##########
        # Cache
        ##########
        self.CACHE_DIR: str = path.abspath(self._table_cache.get("cache_dir").format(
            DATA_DIR=DATA_DIR
        ))
        if not path.isdir(self.CACHE_DIR):
            log.info(f"Creating cache directory: '{self.CACHE_DIR}'")
            mkdir(self.CACHE_DIR)

        lib_cache_path: str = self._table_cache.get("library_cache_file").format(
            DATA_DIR=DATA_DIR,
            CACHE_DIR=self.CACHE_DIR
        )
        self.LIBRARY_CACHE_FILE: Optional[str] = \
            path.abspath(lib_cache_path) \
            if lib_cache_path not in (None, "") \
            else None

        ##########
        # Logging
        ##########
        verbosity: str = self._table_logging.get("verbosity", "").lower()
        self.VERBOSITY: int = logging_name_to_level.get(verbosity)
        if self.VERBOSITY is None:
            log.warning("verbosity was not set properly, falling back to \"info\"")
            self.VERBOSITY = logging.INFO

        self.CACHE_LOG_INTERVAL: int = int(self._table_logging.get("cache_log_interval"))
        self.PARSE_LOG_INTERVAL: int = int(self._table_logging.get("parse_log_interval"))

        ##########
        # FuzzyMacthing
        ##########
        self.FUZZY_MIN_TITLE: int = int(self._table_fuzzy.get("local_library_title_min_match"))
        self.FUZZY_MIN_ALBUM: int = int(self._table_fuzzy.get("local_library_album_min_match"))
        self.FUZZY_MIN_ARTIST: int = int(self._table_fuzzy.get("local_library_artist_min_match"))
        self.FUZZY_YOUTUBE_MIN_TITLE: int = int(self._table_fuzzy.get("youtube_title_min_match"))

        ##########
        # Genres
        ##########
        self.MIN_TAG_WEIGHT: int = int(self._table_genres.get("min_tag_weight"))
        self.MIN_LASTFM_SIMILARITY: int = int(self._table_genres.get("min_lastfm_suggestion_similarity"))
        self.MAX_LASTFM_PAGES: int = int(self._table_genres.get("max_lastfm_pages"))
        self.MAX_GENRE_COUNT: int = int(self._table_genres.get("max_genre_count"))
        # self.GENRES_USE_SPECIFIC = self._table_genres.get("use_most_specific")


raw_config = TOMLConfig.from_filename(CONFIG_FILE)
config = AnalysisConfig(raw_config)

config_pyproject = TOMLConfig.from_filename(PYPROJECT_FILE)
pyproject_tool_poetry = config_pyproject.get_table("tool").get_table("poetry")

PROJECT_NAME = pyproject_tool_poetry.get("name")
VERSION = pyproject_tool_poetry.get("version")
REPOSITORY = pyproject_tool_poetry.get("repository")

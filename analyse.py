import logging
import glob
import time
from os import path
from json import load, dump
from typing import Optional, Dict, List, Any

from mutagen import File, FileType
from openpyxl import Workbook

from core.configuration import config
from core.library import LibraryFile
from core.scrobbledtrack import Scrobble

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

##
# 1. Build music library cache
##

# 1.1) Collect audio files
log.info("Collecting audio files.")


def find_music_library_files(root_dir: str, extensions: tuple) -> List[str]:
    # Recursively build a list of audio files
    globs: List[str] = [path.join(root_dir, f"**/*.{ext_glob}") for ext_glob in extensions]

    files: List[str] = []
    for g in globs:
        files.extend(glob.glob(g, recursive=True))

    files.sort()
    return files


audio_files = find_music_library_files(
    config.MUSIC_LIBRARY_ROOT,
    ("mp3", "ogg", "wav", "flac", "m4a")
)
audio_files_amount = len(audio_files)

# DEBUGONLY
audio_files = audio_files[0:150]

log.info(f"Collected {audio_files_amount} audio files.")

# 1.2) Build audio metadata cache if needed (otherwise just load the previous one)
t_start = time.time()


def build_library_metadata_cache(file_list: List[str]):
    by_album: Dict[str, LibraryFile] = {}
    by_artist: Dict[str, LibraryFile] = {}
    by_track_title: Dict[str, LibraryFile] = {}
    by_track_mbid: Dict[str, LibraryFile] = {}

    counter = 0

    for audio_file in file_list:
        # Load file metadata
        mutagen_file: Optional[FileType] = File(audio_file, easy=True)
        # TODO use json objects instead of full FileType instances
        # ^ we can then save the cache and use it next run without going through the files

        if not mutagen_file:
            raise Exception(f"Error while loading file: {audio_file}")

        lib_file: LibraryFile = LibraryFile.from_mutagen(mutagen_file)

        if lib_file.album_name is not None:
            by_album[lib_file.album_name] = lib_file
        if lib_file.artist_name is not None:
            by_artist[lib_file.artist_name] = lib_file
        if lib_file.track_title is not None:
            by_track_title[lib_file.track_title] = lib_file
        if lib_file.track_mbid is not None:
            by_track_mbid[lib_file.track_mbid] = lib_file

        # Log progress
        if counter % config.CACHE_LOG_INTERVAL == 0:
            log.info(f"Caching progress: {counter} files")
        counter += 1

    return {
        "cache_by_album": by_album,
        "cache_by_artist": by_artist,
        "cache_by_track_title": by_track_title,
        "cache_by_track_mbid": by_track_mbid,
    }


def load_library_metadata():
    with open(config.LIBRARY_CACHE_FILE, "r", encoding="utf8") as lib_file:
        return load(lib_file)


def save_library_metadata(raw: Dict[str, Dict[str, Any]]):
    def serialize_libraryfiles(full: Dict[str, LibraryFile]):
        return {
            k: v.dump() for k, v in full.items()
        }

    dumped = {
        "cache_by_album": serialize_libraryfiles(raw["cache_by_album"]),
        "cache_by_artist": serialize_libraryfiles(raw["cache_by_artist"]),
        "cache_by_track_title": serialize_libraryfiles(raw["cache_by_track_title"]),
        "cache_by_track_mbid": serialize_libraryfiles(raw["cache_by_track_mbid"]),
    }

    with open(config.LIBRARY_CACHE_FILE, "w", encoding="utf8") as lib_file:
        dump(
            dumped,
            lib_file,
            ensure_ascii=False,
        )


# If a cache already exists, load it
# TODO switch to ignore cache? (deleting the cache file also works for now)
if path.isfile(config.LIBRARY_CACHE_FILE):
    log.info("Local library cache found, loading.")
    raw_cache = load_library_metadata()
    log.info("Local library cache loaded.")
else:
    log.info("Building local library cache...")
    raw_cache = build_library_metadata_cache(audio_files)
    save_library_metadata(raw_cache)

# At this point, raw_cache has all the stuff we need
# So we separate it into smaller chunks for later use
cache_by_album: Dict[str, LibraryFile] = raw_cache["cache_by_album"]
cache_by_artist: Dict[str, LibraryFile] = raw_cache["cache_by_artist"]
cache_by_track_title: Dict[str, LibraryFile] = raw_cache["cache_by_track_title"]
cache_by_track_mbid: Dict[str, LibraryFile] = raw_cache["cache_by_track_mbid"]

t_total = round(time.time() - t_start, 1)
log.info(f"Local library cache took {t_total}s")

##
# 2. Load scrobbles
##
log.info("Loading scrobbles file...")
t_start = time.time()


def load_scrobbles(json_file_path: str) -> List:
    with open(json_file_path, "r", encoding="utf8") as scrobbles_file:
        scrobbles_raw = load(scrobbles_file)

    # 2.1) Flatten scrobble pages
    flattened = [item for sublist in scrobbles_raw for item in sublist]
    return flattened


scrobbles = load_scrobbles(config.SCROBBLES_JSON_PATH)
scrobbles_len = len(scrobbles)

t_total = round(time.time() - t_start, 1)
log.info(f"Scrobbles file read and parsed in {t_total}s")
log.info(f"{scrobbles_len} scrobbles loaded.")

##
# 3. Generate statistics
##
log.info("Generating extended data...")
t_start = time.time()

# Create an openpyxl workbook and the data sheet
xl_workbook = Workbook()
sheet = xl_workbook.create_sheet("Data")


# Define search functions
def find_by_mbid(track_mbid: str) -> Scrobble:
    pass


def find_by_metadata(track_title: str, track_album: str, track_artist: str) -> Scrobble:
    pass


def find_on_youtube(track_title: str, track_album: str, track_artist: str) -> Scrobble:
    pass


# Go through every scrobble and append a row for each entry
c = 0
for scrobble in scrobbles:
    s_track_mbid = scrobble.get("mbid")

    s_name = scrobble.get("name")
    s_artist_raw = scrobble.get("artist")
    s_artist = None if s_artist_raw is None else s_artist_raw.get("#text")
    s_album_raw = scrobble.get("album")
    s_album = None if s_album_raw is None else s_album_raw.get("#text")

    # Multiple modes of search:
    # 1) Use track MBID if possible
    # 2) If not possible, fall back to metadata
    # 3) Otherwise, use YouTube search

    # 1)
    if s_track_mbid:
        # Look up the track in cache via mbid
        file = cache_by_track_mbid.get(s_track_mbid)
        if not file:
            # TODO use other methods, separate these into functions
            pass
    # TODO

    # Log progress
    if c % config.PARSE_LOG_INTERVAL == 0:
        log.info(f"Parsing progress: {c} scrobbles")
    c += 1


# Save the workbook to the configured path
xl_workbook.save(filename=config.XLSX_OUTPUT_PATH)

t_total = round(time.time() - t_start, 1)
log.info(f"Spreadsheet generated and saved in {t_total}s")

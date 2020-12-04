import logging
import glob
import time
from os import path
from json import load
from typing import Optional, Dict, List

from mutagen import File, FileType
from openpyxl import Workbook

from core.configuration import config
from core.track import Track

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

# 1.2) Build audio metadata cache
log.info(f"Building metadata cache...")
t_start = time.time()

cache_by_album: Dict[Track] = {}
cache_by_albumartist: Dict[Track] = {}
cache_by_title: Dict[Track] = {}
cache_by_track_mbid: Dict[Track] = {}


def build_library_metadata_cache(file_list: List[str]):
    counter = 0

    for audio_file in file_list:
        # Load file metadata
        tags: Optional[FileType] = File(audio_file, easy=True)
        # TODO use json objects instead of full FileType instances
        # ^ we can then save the cache and use it next run without going through the files

        if not tags:
            raise Exception(f"Error while loading file: {audio_file}")

        track: Track = Track.from_mutagen(tags)

        album = tags.get("album")
        albumartist = tags.get("albumartist")
        title = tags.get("title")
        track_mbid = tags.get("musicbrainz_trackid")

        if album is not None:
            cache_by_album[album[0]] = track
        if albumartist is not None:
            cache_by_albumartist[albumartist[0]] = track
        if title is not None:
            cache_by_title[title[0]] = tags
        if track_mbid is not None:
            cache_by_track_mbid[track_mbid[0]] = track

        # Log progress
        if counter % config.CACHE_LOG_INTERVAL == 0:
            log.info(f"Caching progress: {counter} files")
        counter += 1


build_library_metadata_cache(audio_files)

t_total = round(time.time() - t_start, 1)
log.info(f"Metadata cache built in {t_total}s")

##
# 2. Load scrobbles
##
log.info("Loading scrobbles file...")
t_start = time.time()


def load_scrobbles(json_file_path: str) -> List:
    with open(json_file_path, "r", encoding="utf8") as scrobbles_file:
        scrobbles_raw = load(scrobbles_file)

    # 2.1) Flatten json pages
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
def find_by_mbid(track_mbid: str) -> Track:
    pass


def find_by_metadata(track_title: str, track_album: str, track_artist: str) -> Track:
    pass


def find_on_youtube(track_title: str, track_album: str, track_artist: str) -> Track:
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

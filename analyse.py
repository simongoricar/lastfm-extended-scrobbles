import logging
import glob
import time
from os import path
from json import load, dump
from typing import Optional, Dict, List, Any, Tuple

from mutagen import File, FileType
from openpyxl import Workbook
from fuzzywuzzy.fuzz import ratio
from fuzzywuzzy.process import extractOne

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

log.info(f"Collected {audio_files_amount} audio files.")

# 1.2) Build audio metadata cache if needed (otherwise just load the previous one)
t_start = time.time()


def build_library_metadata_cache(file_list: List[str]):
    by_album: Dict[str, List[LibraryFile]] = {}
    by_artist: Dict[str, List[LibraryFile]] = {}
    by_track_title: Dict[str, List[LibraryFile]] = {}
    by_track_mbid: Dict[str, LibraryFile] = {}

    counter = 0

    for audio_file in file_list:
        # Load file metadata
        mutagen_file: Optional[FileType] = File(audio_file, easy=True)
        if mutagen_file is None:
            raise Exception(f"Error while loading file: {audio_file}")

        lib_file: LibraryFile = LibraryFile.from_mutagen(mutagen_file)

        if lib_file.album_name is not None:
            if lib_file.album_name not in by_album:
                by_album[lib_file.album_name] = [lib_file]
            else:
                by_album[lib_file.album_name].append(lib_file)
        if lib_file.artist_name is not None:
            if lib_file.artist_name not in by_artist:
                by_album[lib_file.artist_name] = [lib_file]
            else:
                by_artist[lib_file.artist_name].append(lib_file)
        if lib_file.track_title is not None:
            if lib_file.track_title not in by_track_title:
                by_track_title[lib_file.track_title] = [lib_file]
            else:
                by_track_title[lib_file.track_title].append(lib_file)
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
        raw = load(lib_file)

    # Convert back into LibraryFile instances
    def instance_libraryfiles_from_list(full: Dict[str, List[Any]]) -> Dict[str, List[LibraryFile]]:
        return {
            k: [LibraryFile(**lib_f) for lib_f in v] for k, v in full.items()
        }

    def instance_libraryfiles_from_single(full: Dict[str, dict]) -> Dict[str, LibraryFile]:
        return {
            k: LibraryFile(**v) for k, v in full.items()
        }

    return {
        "cache_by_album": instance_libraryfiles_from_list(raw["cache_by_album"]),
        "cache_by_artist": instance_libraryfiles_from_list(raw["cache_by_artist"]),
        "cache_by_track_title": instance_libraryfiles_from_list(raw["cache_by_track_title"]),
        "cache_by_track_mbid": instance_libraryfiles_from_single(raw["cache_by_track_mbid"]),
    }


def save_library_metadata(raw: Dict[str, Dict[str, Any]]):
    def serialize_libraryfiles_list(full: Dict[str, List[LibraryFile]]):
        return {
            k: [lib_f.dump() for lib_f in v] for k, v in full.items()
        }

    def serialize_libraryfiles_single(full: Dict[str, LibraryFile]):
        return {
            k: v.dump() for k, v in full.items()
        }

    dumped = {
        "cache_by_album": serialize_libraryfiles_list(raw["cache_by_album"]),
        "cache_by_artist": serialize_libraryfiles_list(raw["cache_by_artist"]),
        "cache_by_track_title": serialize_libraryfiles_list(raw["cache_by_track_title"]),
        "cache_by_track_mbid": serialize_libraryfiles_single(raw["cache_by_track_mbid"]),
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
cache_by_album: Dict[str, List[LibraryFile]] = raw_cache["cache_by_album"]
cache_by_artist: Dict[str, List[LibraryFile]] = raw_cache["cache_by_artist"]
cache_by_track_title: Dict[str, List[LibraryFile]] = raw_cache["cache_by_track_title"]
cache_by_track_mbid: Dict[str, LibraryFile] = raw_cache["cache_by_track_mbid"]

# Now build some more cache
cache_list_of_albums: List[str] = list(cache_by_album.keys())
cache_list_of_artists: List[str] = list(cache_by_artist.keys())
cache_list_of_track_titles: List[str] = list(cache_by_track_title.keys())

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
# 3. Generate data and dump it into a spreadsheet
##
log.info("Generating extended data...")
t_start = time.time()

# Create an openpyxl workbook and the data sheet
xl_workbook = Workbook()
sheet = xl_workbook.create_sheet("Data")


# Define search functions
def find_by_mbid(raw_scrobble: Dict[str, Any], track_mbid: str) -> Optional[Scrobble]:
    library_track = cache_by_track_mbid.get(track_mbid)

    if library_track is None:
        return None
    else:
        return Scrobble.from_library_track(raw_scrobble, library_track)


def find_by_metadata(
        raw_scrobble: Dict[str, Any],
        track_title: str, track_album: str, track_artist: str
) -> Optional[Scrobble]:
    # Find the best title, album and artist match in the local library cache
    # As a fallback, use the file name

    # Start by filtering by closest track name match
    # Pick best with fuzzywuzzy

    # TODO test this a bit, especially the score_cutoff value
    best_match: Optional[Tuple[str, int]] = extractOne(
        track_title,
        cache_list_of_track_titles,
        scorer=ratio,
        score_cutoff=config.FUZZY_MIN_TITLE
    )

    if best_match is None:
        return None

    # If a match was found, try to match it with the correct artist and album
    tracks: List[LibraryFile] = cache_by_track_title[best_match[0]]

    for track in tracks:
        artist_match = ratio(track_artist, track.artist_name)
        album_match = ratio(track_album, track.album_name)

        if artist_match >= config.FUZZY_MIN_ARTIST and album_match >= config.FUZZY_MIN_ALBUM:
            # This match is good enough
            return Scrobble.from_library_track(raw_scrobble, track)


    # Returns None only if no sufficiently matching track could be found
    return None


def find_on_youtube(track_title: str, track_album: str, track_artist: str) -> Optional[Scrobble]:
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

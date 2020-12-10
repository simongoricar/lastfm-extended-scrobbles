import logging
from core.configuration import config
logging.basicConfig(level=config.VERBOSITY)

import glob
import time
from os import path
from json import load, dump
from typing import Optional, Dict, List, Any, Tuple

from mutagen import File, FileType, MutagenError
from openpyxl import Workbook
from fuzzywuzzy.fuzz import ratio, partial_ratio
from fuzzywuzzy.process import extractOne
from youtubesearchpython import SearchVideos

from core.library import LibraryFile
from core.scrobble import ExtendedScrobble, TrackSourceType, RawScrobble
from core.utilities import youtube_length_to_sec, get_best_attribute
from core.musicbrainz import ReleaseTrack
from core.genres import fetch_genre_by_metadata

log = logging.getLogger(__name__)

##
# 1. Build music library cache
##

# 1.1) Collect audio files
log.info("[STEP 1] Collecting audio files.")


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

    files_successful = 0
    files_failed = 0

    counter = 0

    for audio_file in file_list:
        # Load file metadata
        try:
            mutagen_file: Optional[FileType] = File(audio_file, easy=True)
        except MutagenError:
            # Failed to load the file, skip it
            log.warning(f"Failed to load audio file: \"{audio_file}\"")
            files_failed += 1
            continue
        else:
            files_successful += 1

        if mutagen_file is None:
            log.warning(f"Audio file type could not be determined: \"{audio_file}\"")
            files_failed += 1
            continue

        lib_file: LibraryFile = LibraryFile.from_mutagen(mutagen_file)

        if lib_file.album_name is not None:
            if lib_file.album_name not in by_album:
                by_album[lib_file.album_name] = [lib_file]
            else:
                by_album[lib_file.album_name].append(lib_file)
        if lib_file.artist_name is not None:
            if lib_file.artist_name not in by_artist:
                by_artist[lib_file.artist_name] = [lib_file]
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
        counter += 1
        if counter % config.CACHE_LOG_INTERVAL == 0:
            log.info(f"Caching progress: {counter} files")

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
    log.info("Local music library cache found, loading.")
    raw_cache = load_library_metadata()
    log.info("Local music library cache loaded.")
elif config.LIBRARY_CACHE_FILE != "":
    log.info("Building local music library cache...")
    raw_cache = build_library_metadata_cache(audio_files)
    save_library_metadata(raw_cache)
else:
    raw_cache = {"cache_by_album": [], "cache_by_artist": [], "cache_by_track_title": [], "cache_by_track_mbid": []}
    log.info("Local music library search is disabled.")

# At this point, raw_cache has all the stuff we need
# So we separate it into smaller chunks for later use
cache_by_album: Dict[str, List[LibraryFile]] = raw_cache["cache_by_album"]
cache_by_artist: Dict[str, List[LibraryFile]] = raw_cache["cache_by_artist"]
cache_by_track_title: Dict[str, List[LibraryFile]] = raw_cache["cache_by_track_title"]
cache_by_track_mbid: Dict[str, LibraryFile] = raw_cache["cache_by_track_mbid"]

# Now build some more cache
cache_list_of_albums: List[str] = [str(a) for a in cache_by_album.keys()]
cache_list_of_artists: List[str] = [str(a) for a in cache_by_artist.keys()]
cache_list_of_track_titles: List[str] = [str(a) for a in cache_by_track_title.keys()]

t_total = round(time.time() - t_start, 1)
log.info(f"Local library cache took {t_total}s")

##
# 2. Load scrobbles
##
log.info("[STEP 2] Loading scrobbles file...")
t_start = time.time()


# TODO data from the tools linked in readme doesn't include the extended data (loved tracks)
#   Look into getting that data as well
#   Maybe lastfm-extended-scrobbles could download that data for you as well
#   so you don't need to depend on external sources?
def load_scrobbles(json_file_path: str) -> List:
    with open(json_file_path, "r", encoding="utf8") as scrobbles_file:
        scrobbles_raw = load(scrobbles_file)

    # 2.1) Flatten scrobble pages
    flattened = [item for sublist in scrobbles_raw for item in sublist]
    return flattened


# TODO option to filter scrobbles by date (from, to)
scrobbles = load_scrobbles(config.SCROBBLES_JSON_PATH)
scrobbles_len = len(scrobbles)

t_total = round(time.time() - t_start, 1)
log.info(f"Scrobbles file read and parsed in {t_total}s")
log.info(f"{scrobbles_len} scrobbles loaded.")

##
# 3. Generate data and dump it into a spreadsheet
##
log.info("[STEP 3] Generating extended data...")
t_start = time.time()

# Create an openpyxl workbook and the data sheet
xl_workbook = Workbook()
sheet = xl_workbook.active
sheet.title = "Data"

# Search caches
# This cache really pays off if the tracks repeat (over a longer period of time for example)
# TODO implement a better cache than this
#   cache should probably carry over restarts, but we need a TTL

# Dict[query, duration]
youtube_cache_by_query: Dict[str, int] = {}
# Dict[(title, album, artist), LibraryFile]
local_library_cache_by_metadata: Dict[Tuple[str, str, str], Optional[LibraryFile]] = {}


# Define search functions
def find_by_mbid(raw_scrobble: RawScrobble) -> Optional[ExtendedScrobble]:
    library_track = cache_by_track_mbid.get(raw_scrobble.track_mbid)

    if library_track is None:
        return None
    else:
        return ExtendedScrobble.from_library_track(raw_scrobble, library_track, TrackSourceType.LOCAL_LIBRARY_MBID)


def find_by_metadata(
        raw_scrobble: RawScrobble,
) -> Optional[ExtendedScrobble]:
    # TODO decorator for caching the results
    # Find the best title, album and artist match in the local library cache
    # TODO use filename as fallback

    # Use cached result if possible
    caching_tuple = (raw_scrobble.track_title, raw_scrobble.album_title, raw_scrobble.artist_name)
    if caching_tuple in local_library_cache_by_metadata:
        log.debug("find_by_metadata: cache hit")
        track: Optional[LibraryFile] = local_library_cache_by_metadata[caching_tuple]

        if track is None:
            return None
        else:
            return ExtendedScrobble.from_library_track(raw_scrobble, track, TrackSourceType.LOCAL_LIBRARY_METADATA)

    log.debug("find_by_metadata: cache miss")
    # Start by filtering to the closest artist name match
    best_artist_match: Optional[Tuple[str, int]] = extractOne(
        raw_scrobble.artist_name,
        cache_list_of_artists,
        scorer=ratio,
        score_cutoff=config.FUZZY_MIN_ARTIST
    )

    # Edge case: if no match can be found, we should stop
    if best_artist_match is None:
        local_library_cache_by_metadata[caching_tuple] = None
        return None

    # Otherwise, build a list of LibraryFiles for further filtering
    current_cache_list: List[LibraryFile] = cache_by_artist[best_artist_match[0]]

    # Now filter by album if possible
    if raw_scrobble.album_title not in (None, ""):
        albums = list(set([a.album_name for a in current_cache_list]))
        best_album_match: Optional[Tuple[str, int]] = extractOne(
            raw_scrobble.album_title,
            albums,
            scorer=ratio,
            score_cutoff=config.FUZZY_MIN_ALBUM
        )

        # If a match is found, filter the list by this album
        if best_album_match is not None:
            current_cache_list = [a for a in current_cache_list if a.album_name == best_album_match[0]]

    # Finally, choose the best track by title
    c_to_track_titles = list(set([a.track_title for a in current_cache_list]))
    best_track_match: Optional[Tuple[str, int]] = extractOne(
        raw_scrobble.track_title,
        c_to_track_titles,
        scorer=ratio,
        score_cutoff=config.FUZZY_MIN_TITLE
    )

    # Edge case: no title match, exit here
    if best_track_match is None:
        local_library_cache_by_metadata[caching_tuple] = None
        return None

    # Otherwise build a ExtendedScrobble with this information
    final_track = current_cache_list[c_to_track_titles.index(best_track_match[0])]

    return ExtendedScrobble.from_library_track(raw_scrobble, final_track, TrackSourceType.LOCAL_LIBRARY_METADATA)


def find_on_musicbrainz(raw_scrobble: RawScrobble) -> Optional[ExtendedScrobble]:
    release_track = ReleaseTrack.from_track_mbid(raw_scrobble.track_mbid)
    if release_track is None:
        return None

    log.debug(f"find_on_musicbrainz: got release track")
    return ExtendedScrobble.from_musicbrainz_track(raw_scrobble, release_track)


def find_on_youtube(
        raw_scrobble: RawScrobble
) -> Optional[ExtendedScrobble]:
    # Search YouTube for the closest "artist title" match
    query = f"{raw_scrobble.artist_name} {raw_scrobble.album_title} {raw_scrobble.track_title}"

    if query in youtube_cache_by_query:
        log.debug("YouTube: using cached search")
        duration_sec = youtube_cache_by_query[query]
    else:
        search = SearchVideos(query, mode="list", max_results=8)

        # Find the closest match
        closest_match = extractOne(
            query,
            search.titles,
            scorer=partial_ratio,
            score_cutoff=config.FUZZY_YOUTUBE_MIN_TITLE
        )

        if closest_match is None:
            log.debug("YouTube: no hit")
            return None
        else:
            log.debug("YouTube: got a hit")

        # Parse the closest one into a proper ExtendedScrobble
        index = search.titles.index(closest_match[0])
        duration_human = search.durations[index]
        duration_sec = youtube_length_to_sec(duration_human)

        youtube_cache_by_query[query] = duration_sec

    return ExtendedScrobble.from_youtube(raw_scrobble, duration_sec)


# Append the header
sheet.append(ExtendedScrobble.spreadsheet_header())

# Go through every scrobble and append a row for each entry
c_local_mbid_hits = 0
c_local_metadata_hits = 0
c_musicbrainz_hits = 0
c_youtube_hits = 0
c_basic_info_hits = 0

c = 0
for scrobble_raw_data in scrobbles:
    rs: RawScrobble = RawScrobble.from_raw_data(scrobble_raw_data)

    #########
    # STEP 1: Find source
    #########
    # Multiple modes of search, first has highest priority:
    # 1) Use track MBID (local library)
    # 2) Use track metadata (local library)
    # 3) Use track MBID (search on MusicBrainz)
    # 3) Use track metadata (YouTube search)
    scrobble: Optional[ExtendedScrobble] = None

    # Try local track mbid search
    if rs.track_mbid is not None:
        # Look up the track in cache via mbid
        scrobble = find_by_mbid(rs)
        if scrobble is not None:
            log.debug(f"Match by MBID (local library): "
                      f"{rs.artist_name} - {rs.album_title} - {rs.track_title} ({rs.track_mbid})")
            c_local_mbid_hits += 1

    # Try local metadata search
    if scrobble is None and rs.track_title is not None:
        scrobble = find_by_metadata(rs)

        if scrobble is not None:
            log.debug(f"Match by metadata (local library): "
                      f"{rs.artist_name} - {rs.album_title} - {rs.track_title} ({rs.track_mbid})")
            c_local_metadata_hits += 1

    # Try MusicBrainz
    if scrobble is None and rs.track_mbid is not None:
        scrobble = find_on_musicbrainz(rs)

        if scrobble is not None:
            log.debug(f"Match by MBID (MusicBrainz): "
                      f"{rs.artist_name} - {rs.album_title} - {rs.track_title} ({rs.track_mbid})")
            c_musicbrainz_hits += 1

    # Try youtube search
    if scrobble is None:
        log.debug("Trying YouTube search.")
        scrobble = find_on_youtube(rs)

        if scrobble is not None:
            log.debug(f"Match by metadata (YouTube): "
                      f"{rs.artist_name} - {rs.album_title} - {rs.track_title} ({rs.track_mbid})")
            c_youtube_hits += 1

    # If absolutely no match can be found, create a fallback scrobble with just the basic data
    if scrobble is None:
        log.debug("No match, using basic scrobble data.")
        scrobble = ExtendedScrobble.from_basic_data(rs)
        c_basic_info_hits += 1

    #########
    # STEP 2: Find genre if needed
    #########
    if scrobble.genre_list is None:
        log.debug("Fetching Last.fm genres.")

        genres: List[str] = fetch_genre_by_metadata(
            scrobble.track_title,
            scrobble.album_name,
            scrobble.artist_name,
        )
        scrobble.genre_list = genres

    # TODO add a "loved track" column
    # Finally, dump this scrobble data into the next spreadsheet row
    sheet.append(scrobble.to_spreadsheet_list())

    # Log progress
    c += 1
    if c % config.PARSE_LOG_INTERVAL == 0:
        log.info(f"Parsing progress: {c} scrobbles ({round(c / scrobbles_len * 100, 1)}%)")


# Save the workbook to the configured path
c = 0
written = False

while c < 5:
    try:
        xl_workbook.save(filename=config.XLSX_OUTPUT_PATH)
        written = True
        break
    except PermissionError:
        log.warning("PermissionError while trying to open spreadsheet file, retrying in 5 seconds.")
        time.sleep(5)
        c += 1

if written is False:
    log.critical(f"Failed to write spreadsheet file to \"{config.XLSX_OUTPUT_PATH}\" after 5 retries.")
    exit(1)

t_total = round(time.time() - t_start, 1)
log.info(f"Spreadsheet generated and saved in {t_total}s")
log.info(f"Spreadsheet location: \"{config.XLSX_OUTPUT_PATH}\"")

perc_local_mbid_hits = round(c_local_mbid_hits / scrobbles_len * 100, 1)
perc_local_metadata_hits = round(c_local_metadata_hits / scrobbles_len * 100, 1)
perc_musicbrainz_hits = round(c_musicbrainz_hits / scrobbles_len * 100, 1)
perc_youtube_hits = round(c_youtube_hits / scrobbles_len * 100, 1)
perc_basic_info = round(c_basic_info_hits / scrobbles_len * 100, 1)

log.info(f"Source statistics:\n"
         f"  Local library (MBID): {c_local_mbid_hits} ({perc_local_mbid_hits}%)\n"
         f"  Local library (metadata): {c_local_metadata_hits} ({perc_local_metadata_hits}%)\n"
         f"  MusicBrainz: {c_musicbrainz_hits} ({perc_musicbrainz_hits}%)\n"
         f"  YouTube: {c_youtube_hits} ({perc_youtube_hits}%)\n"
         f"  No matches, just basic data: {c_basic_info_hits} ({perc_basic_info}%)")

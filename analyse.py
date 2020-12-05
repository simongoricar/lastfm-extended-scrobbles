import logging
import glob
import time
from os import path
from json import load, dump
from typing import Optional, Dict, List, Any, Tuple

from mutagen import File, FileType
from openpyxl import Workbook
from fuzzywuzzy.fuzz import ratio, partial_ratio, UWRatio
from fuzzywuzzy.process import extractOne
from youtubesearchpython import SearchVideos

from core.configuration import config
from core.library import LibraryFile
from core.scrobble import Scrobble, TrackSourceType
from core.utilities import youtube_length_to_sec
from core.musicbrainz import ReleaseTrack

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
cache_list_of_albums: List[str] = [str(a) for a in cache_by_album.keys()]
cache_list_of_artists: List[str] = [str(a) for a in cache_by_artist.keys()]
cache_list_of_track_titles: List[str] = [str(a) for a in cache_by_track_title.keys()]

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

# DEBUGONLY
scrobbles = scrobbles[1000:2000]

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
sheet = xl_workbook.active
sheet.title = "Data"

# Search caches
# This cache really pays off if the tracks repeat (over a longer period of time for example)
# TODO implement a better cache than this

# Dict[query, duration]
youtube_cache_by_query: Dict[str, int] = {}
# Dict[(title, album, artist), LibraryFile]
local_library_cache_by_metadata: Dict[Tuple[str, str, str], Optional[LibraryFile]] = {}


# Define search functions
def find_by_mbid(raw_scrobble: Dict[str, Any], track_mbid: str) -> Optional[Scrobble]:
    library_track = cache_by_track_mbid.get(track_mbid)

    if library_track is None:
        return None
    else:
        return Scrobble.from_library_track(raw_scrobble, library_track, TrackSourceType.LOCAL_LIBRARY_MBID)


def find_by_metadata(
        raw_scrobble: Dict[str, Any],
        track_title: str, track_album: str, track_artist: str
) -> Optional[Scrobble]:
    # Find the best title, album and artist match in the local library cache
    # TODO use filename as fallback

    # Use cached result if possible
    caching_tuple = (track_title, track_album, track_artist)
    if caching_tuple in local_library_cache_by_metadata:
        log.debug("find_by_metadata: cache hit")
        track: Optional[LibraryFile] = local_library_cache_by_metadata[caching_tuple]

        if track is None:
            return None
        else:
            return Scrobble.from_library_track(raw_scrobble, track, TrackSourceType.LOCAL_LIBRARY_METADATA)
    else:
        log.debug("find_by_metadata: cache miss")
        # Start by filtering by closest track name match
        # Pick best with fuzzywuzzy
        best_match: Optional[Tuple[str, int]] = extractOne(
            track_title,
            cache_list_of_track_titles,
            scorer=ratio,
            score_cutoff=config.FUZZY_MIN_TITLE
        )

        if best_match is None:
            return None

        # If a match was found, try to match it with the correct artist and album
        log.debug(f"find_by_metadata: got match with similarity {best_match[1]}")
        tracks: List[LibraryFile] = cache_by_track_title[best_match[0]]

        for track in tracks:
            artist_match = UWRatio(track_artist, track.artist_name)
            album_match = UWRatio(track_album, track.album_name)

            if artist_match >= config.FUZZY_MIN_ARTIST and album_match >= config.FUZZY_MIN_ALBUM:
                # This match is good enough, save it into cache before returning the new Scrobble
                local_library_cache_by_metadata[caching_tuple] = track
                return Scrobble.from_library_track(raw_scrobble, track, TrackSourceType.LOCAL_LIBRARY_METADATA)

        # Returns None only if no sufficiently matching track could be found
        local_library_cache_by_metadata[caching_tuple] = None
        return None


def find_on_musicbrainz(raw_scrobble: Dict[str, Any], track_mbid: str) -> Optional[Scrobble]:
    release_track = ReleaseTrack.from_track_mbid(track_mbid)
    if release_track is None:
        return None

    log.debug(f"find_on_musicbrainz: got release track")
    return Scrobble.from_musicbrainz_track(raw_scrobble, release_track)


def find_on_youtube(
        raw_scrobble: Dict[str, Any],
        track_title: str,
        track_artist: str
) -> Optional[Scrobble]:
    # Search YouTube for the closest "artist title" match
    query = f"{track_artist} {track_title}"

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

        # Parse the closest one into a proper Scrobble
        index = search.titles.index(closest_match[0])
        duration_human = search.durations[index]
        duration_sec = youtube_length_to_sec(duration_human)

        youtube_cache_by_query[query] = duration_sec

    return Scrobble.from_youtube(raw_scrobble, duration_sec)


# Go through every scrobble and append a row for each entry
sheet.append(Scrobble.spreadsheet_header())

c_local_mbid_hits = 0
c_local_metadata_hits = 0
c_musicbrainz_hits = 0
c_youtube_hits = 0
c_basic_info = 0

c = 0
for scrobble_raw in scrobbles:
    s_track_mbid = scrobble_raw.get("mbid")

    s_name = scrobble_raw.get("name")
    s_artist_raw = scrobble_raw.get("artist")
    s_artist = None if s_artist_raw is None else s_artist_raw.get("#text")
    s_album_raw = scrobble_raw.get("album")
    s_album = None if s_album_raw is None else s_album_raw.get("#text")

    # Multiple modes of search, first has highest priority:
    # 1) Use track MBID (local library)
    # 2) Use track metadata (local library)
    # 3) Use track MBID (search on MusicBrainz)
    # 3) Use track metadata (YouTube search)
    scrobble = None

    # Try local track mbid search
    if s_track_mbid:
        # Look up the track in cache via mbid
        scrobble = find_by_mbid(scrobble_raw, s_track_mbid)
        if scrobble is not None:
            log.debug(f"Match by MBID (local library): {s_artist} - {s_album} - {s_name} ({s_track_mbid})")
            c_local_mbid_hits += 1

    # Try local metadata search
    if scrobble is None and s_name is not None:
        scrobble = find_by_metadata(scrobble_raw, s_name, s_album, s_artist)

        if scrobble is not None:
            log.debug(f"Match by metadata (local library): {s_artist} - {s_album} - {s_name} ({s_track_mbid})")
            c_local_metadata_hits += 1

    # Try MusicBrainz
    if scrobble is None and s_track_mbid not in (None, ""):
        scrobble = find_on_musicbrainz(scrobble_raw, s_track_mbid)

        if scrobble is not None:
            log.debug(f"Match by MBID (MusicBrainz): {s_artist} - {s_album} - {s_name} ({s_track_mbid})")

    # Try youtube search
    if scrobble is None:
        log.debug("Trying YouTube search.")
        scrobble = find_on_youtube(scrobble_raw, s_name, s_artist)

        if scrobble is not None:
            log.debug(f"Match by metadata (YouTube): {s_artist} - {s_name}")
            c_youtube_hits += 1

    # If absolutely no match can be found, create a fallback scrobble with just the basic data
    if scrobble is None:
        log.debug("No match, using basic scrobble data.")
        scrobble = Scrobble.from_basic_data(scrobble_raw)
        c_basic_info += 1

    # Finally, dump this scrobble data into the next spreadsheet row
    sheet.append(scrobble.to_spreadsheet_list())

    # Log progress
    c += 1
    if c % config.PARSE_LOG_INTERVAL == 0:
        log.info(f"Parsing progress: {c} scrobbles ({round(c / scrobbles_len * 100, 1)}%)")


# Save the workbook to the configured path
c = 0
while c < 5:
    try:
        xl_workbook.save(filename=config.XLSX_OUTPUT_PATH)
        break
    except PermissionError:
        log.warning("PermissionError while trying to open spreadsheet file, retrying in 5 seconds.")
        time.sleep(5)
        c += 1

t_total = round(time.time() - t_start, 1)
log.info(f"Spreadsheet generated and saved in {t_total}s")

perc_local_mbid_hits = round(c_local_mbid_hits / scrobbles_len * 100, 1)
perc_local_metadata_hits = round(c_local_metadata_hits / scrobbles_len * 100, 1)
perc_musicbrainz_hits = round(c_musicbrainz_hits / scrobbles_len * 100, 1)
perc_youtube_hits = round(c_youtube_hits / scrobbles_len * 100, 1)
perc_basic_info = round(c_basic_info / scrobbles_len * 100, 1)

log.info(f"Statistics:\n"
         f"  Local library (MBID): {c_local_mbid_hits} ({perc_local_mbid_hits}%)\n"
         f"  Local library (metadata): {c_local_metadata_hits} ({perc_local_metadata_hits}%)\n"
         f"  MusicBrainz: {c_musicbrainz_hits} ({perc_musicbrainz_hits}%)\n"
         f"  YouTube: {c_youtube_hits} ({perc_youtube_hits}%)\n"
         f"  No matches, just basic data: {c_basic_info} ({perc_basic_info}%)")

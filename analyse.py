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
from fuzzywuzzy.fuzz import partial_ratio, UQRatio
from fuzzywuzzy.process import extractOne
from youtubesearchpython import SearchVideos

from core.library import LibraryFile
from core.scrobble import ExtendedScrobble, TrackSourceType, RawScrobble
from core.utilities import youtube_length_to_sec
from core.musicbrainz import ReleaseTrack
from core.genres import fetch_genre_by_metadata
from core.prevent_sleep import inhibit, uninhibit
from core.state import State

log = logging.getLogger(__name__)


##
# Cache the music library
##
def find_music_library_files(root_dir: str) -> List[str]:
    # Recursively build a list of audio files
    globs: List[str] = [
        path.join(root_dir, f"**/*.{ext_glob}")
        for ext_glob in ("mp3", "ogg", "wav", "flac", "m4a")
    ]

    files: List[str] = []
    for g in globs:
        files.extend(glob.glob(g, recursive=True))

    files.sort()
    return files


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


def ensure_library_cache(state: State):
    """
    Makes sure the music library cache exists.
    Generates one if needed, otherwise loads from file.

    Args:
        state:
            State instance to save the cache into.

            Keys that are saved (all but one are of type Dict[str, List[LibraryFile]]):
                - cache_by_album (keys are album titles)
                - cache_by_artist (keys are artist names)
                - cache_by_track_title (keys are track titles)
                - cache_by_track_mbid (keys are track MBIDs)
                    This is the only attribute that is Dict[str, LibraryFile].
    """
    # Build audio metadata cache if needed (otherwise just load the json cache)
    t_start = time.time()

    # If a cache already exists, load it
    # TODO switch to ignore cache? (deleting the cache file also works for now)
    if path.isfile(config.LIBRARY_CACHE_FILE):
        log.info("Local music library cache found, loading.")
        raw_cache = load_library_metadata()
        log.info("Local music library cache loaded.")
    elif config.LIBRARY_CACHE_FILE not in (None, ""):
        log.info("Collecting audio files...")
        file_list: List[str] = find_music_library_files(config.MUSIC_LIBRARY_ROOT)
        log.info(f"Collected {len(file_list)} audio files.")

        log.info("Building local music library cache...")
        raw_cache = build_library_metadata_cache(file_list)
        save_library_metadata(raw_cache)
    else:
        raw_cache = {"cache_by_album": [], "cache_by_artist": [], "cache_by_track_title": [], "cache_by_track_mbid": []}
        log.info("Local music library search is disabled.")

    # At this point, raw_cache has all the stuff we need
    # So we separate it into smaller chunks for saving into state

    # All Dict[str, List[LibraryFile]]
    state.cache_by_album = raw_cache["cache_by_album"]
    state.cache_by_artist = raw_cache["cache_by_artist"]
    state.cache_by_track_title = raw_cache["cache_by_track_title"]
    # Dict[str, LibraryFile]
    state.cache_by_track_mbid = raw_cache["cache_by_track_mbid"]

    # Build a little bit more cache
    # TODO make a module for all these caches

    # All are List[str]
    state.cache_list_of_albums = [str(a) for a in state.cache_by_album.keys()]
    state.cache_list_of_artists = [str(a) for a in state.cache_by_artist.keys()]
    # TODO cache_list_of_track_titles -> cache_list_of_tracks
    state.cache_list_of_tracks = [str(a) for a in state.cache_by_track_title.keys()]

    # cache_list_of_albums: List[str] = [str(a) for a in cache_by_album.keys()]
    # cache_list_of_artists: List[str] = [str(a) for a in cache_by_artist.keys()]
    # cache_list_of_track_titles: List[str] = [str(a) for a in cache_by_track_title.keys()]

    t_total = round(time.time() - t_start, 1)
    log.info(f"Local library cache took {t_total}s")


##
# Scrobbles
##
def load_scrobbles(state: State):
    """
    Load the scrobbles file into JSON and flatten it.

    Args:
        state:
            State instance to save the scrobbles into.
            Keys:
                - scrobbles (type: List[Dict[Any, Any]])
    """
    def load_and_flatten(json_file_path: str) -> List:
        with open(json_file_path, "r", encoding="utf8") as scrobbles_file:
            scrobbles_raw = load(scrobbles_file)

        # Flatten scrobble pages into a big list
        flattened = [item for sublist in scrobbles_raw for item in sublist]
        return flattened

    log.info("[STEP 2] Loading scrobbles file...")
    t_start = time.time()

    # TODO option to filter scrobbles by date (from, to)
    scrobbles = load_and_flatten(config.SCROBBLES_JSON_PATH)
    # Save into state
    state.scrobbles = scrobbles

    t_total = round(time.time() - t_start, 1)
    log.info(f"Scrobbles file read and parsed in {t_total}s")
    log.info(f"{len(scrobbles)} scrobbles loaded.")


##
# Extended data
##

# Define search functions
def find_by_mbid(state: State, raw_scrobble: RawScrobble) -> Optional[ExtendedScrobble]:
    library_track = state.cache_by_track_mbid.get(raw_scrobble.track_mbid)

    if library_track is None:
        return None
    else:
        return ExtendedScrobble.from_library_track(raw_scrobble, library_track, TrackSourceType.LOCAL_LIBRARY_MBID)


def _find_by_metadata_full_match(state: State, raw_scrobble: RawScrobble) -> Optional[ExtendedScrobble]:
    if raw_scrobble.track_title in state.cache_by_track_title:
        # First, match by track title, then filter by artist and album if possible
        track_matches: List[LibraryFile] = state.cache_by_track_title[raw_scrobble.track_title]

        if len(track_matches) < 1:
            return None
        elif len(track_matches) == 1:
            return ExtendedScrobble.from_library_track(
                raw_scrobble, track_matches[0], TrackSourceType.LOCAL_LIBRARY_METADATA
            )

        # First: by artist
        track_matches = [m for m in track_matches if m.artist_name == raw_scrobble.artist_name]

        if len(track_matches) < 1:
            return None
        elif len(track_matches) == 1:
            return ExtendedScrobble.from_library_track(
                raw_scrobble, track_matches[0], TrackSourceType.LOCAL_LIBRARY_METADATA
            )

        # Then: by album
        track_matches = [m for m in track_matches if m.album_name == raw_scrobble.album_title]

        if len(track_matches) < 1:
            return None
        elif len(track_matches) == 1:
            return ExtendedScrobble.from_library_track(
                raw_scrobble, track_matches[0], TrackSourceType.LOCAL_LIBRARY_METADATA
            )
        else:
            # Still multiple matches
            log.warning(f"Multiple matches when trying full metadata match, returning None. "
                        f"(\"{raw_scrobble}\" fully matches: {track_matches})")
            return None

    return None


def _find_by_metadata_partial_match(
        state: State,
        raw_scrobble: RawScrobble
) -> Optional[ExtendedScrobble]:
    # Use cached result if possible
    caching_tuple = (raw_scrobble.track_title, raw_scrobble.album_title, raw_scrobble.artist_name)
    if caching_tuple in state.local_cache_by_partial_metadata:
        log.debug("_find_by_metadata_partial_match: cache hit")
        track: Optional[LibraryFile] = state.local_cache_by_partial_metadata[caching_tuple]

        if track is None:
            return None
        else:
            return ExtendedScrobble.from_library_track(raw_scrobble, track, TrackSourceType.LOCAL_LIBRARY_METADATA)

    log.debug("_find_by_metadata_partial_match: cache miss")
    # Start by filtering to the closest artist name match
    best_artist_match: Optional[Tuple[str, int]] = extractOne(
        raw_scrobble.artist_name,
        state.cache_list_of_artists,
        scorer=UQRatio,
        score_cutoff=config.FUZZY_MIN_ARTIST
    )

    # Edge case: if no match can be found, we should stop
    if best_artist_match is None:
        state.local_cache_by_partial_metadata[caching_tuple] = None
        return None

    # Otherwise, build a list of LibraryFiles for further filtering
    current_cache_list: List[LibraryFile] = state.cache_by_artist[best_artist_match[0]]

    # Now filter by album if possible
    if raw_scrobble.album_title not in (None, ""):
        albums: List[str] = list(set([str(a.album_name) for a in current_cache_list]))
        best_album_match: Optional[Tuple[str, int]] = extractOne(
            raw_scrobble.album_title,
            albums,
            scorer=UQRatio,
            score_cutoff=config.FUZZY_MIN_ALBUM
        )

        # If a match is found, filter the list by this album
        if best_album_match is not None:
            current_cache_list = [a for a in current_cache_list if a.album_name == best_album_match[0]]

    # Finally, choose the best track by title
    c_to_track_titles = list(set([str(a.track_title) for a in current_cache_list]))
    best_track_match: Optional[Tuple[str, int]] = extractOne(
        raw_scrobble.track_title,
        c_to_track_titles,
        scorer=UQRatio,
        score_cutoff=config.FUZZY_MIN_TITLE
    )

    # Edge case: no title match, exit here
    if best_track_match is None:
        state.local_cache_by_partial_metadata[caching_tuple] = None
        return None

    # Otherwise build a ExtendedScrobble with this information
    final_track = current_cache_list[c_to_track_titles.index(best_track_match[0])]

    return ExtendedScrobble.from_library_track(raw_scrobble, final_track, TrackSourceType.LOCAL_LIBRARY_METADATA)


def find_by_metadata(
        state: State,
        raw_scrobble: RawScrobble,
) -> Optional[ExtendedScrobble]:
    # TODO decorator for caching the results
    # Find the best title, album and artist match in the local library cache
    # TODO use filename as fallback

    #######
    # 1) Try full match first
    #######
    sc: Optional[ExtendedScrobble] = _find_by_metadata_full_match(state, raw_scrobble)

    #######
    # 2) Try a partial match
    #######
    if sc is None:
        sc = _find_by_metadata_partial_match(state, raw_scrobble)

    return sc



def find_on_musicbrainz(raw_scrobble: RawScrobble) -> Optional[ExtendedScrobble]:
    release_track = ReleaseTrack.from_track_mbid(raw_scrobble.track_mbid)
    if release_track is None:
        return None

    log.debug(f"find_on_musicbrainz: got release track")
    return ExtendedScrobble.from_musicbrainz_track(raw_scrobble, release_track)


def find_on_youtube(
        state: State,
        raw_scrobble: RawScrobble
) -> Optional[ExtendedScrobble]:
    # Search YouTube for the closest "artist title" match
    query = f"{raw_scrobble.artist_name} {raw_scrobble.album_title} {raw_scrobble.track_title}"

    if query in state.youtube_cache_by_query:
        log.debug("YouTube: using cached search")
        duration_sec = state.youtube_cache_by_query[query]
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

        state.youtube_cache_by_query[query] = duration_sec

    return ExtendedScrobble.from_youtube(raw_scrobble, duration_sec)


def process_single_scrobble(state: State, raw_data: Dict[Any, Any]) -> ExtendedScrobble:
    rs: RawScrobble = RawScrobble.from_raw_data(raw_data)

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
        scrobble = find_by_mbid(state, rs)
        if scrobble is not None:
            log.debug(f"Match by MBID (local library): "
                      f"{rs.artist_name} - {rs.album_title} - {rs.track_title} ({rs.track_mbid})")
            state.c_local_mbid_hits += 1

    # Try local metadata search
    if scrobble is None and rs.track_title is not None:
        scrobble = find_by_metadata(state, rs)

        if scrobble is not None:
            log.debug(f"Match by metadata (local library): "
                      f"{rs.artist_name} - {rs.album_title} - {rs.track_title} ({rs.track_mbid})")
            state.c_local_metadata_hits += 1

    # Try MusicBrainz
    if scrobble is None and rs.track_mbid is not None:
        scrobble = find_on_musicbrainz(rs)

        if scrobble is not None:
            log.debug(f"Match by MBID (MusicBrainz): "
                      f"{rs.artist_name} - {rs.album_title} - {rs.track_title} ({rs.track_mbid})")
            state.c_musicbrainz_hits += 1

    # Try youtube search
    if scrobble is None:
        log.debug("Trying YouTube search.")
        scrobble = find_on_youtube(state, rs)

        if scrobble is not None:
            log.debug(f"Match by metadata (YouTube): "
                      f"{rs.artist_name} - {rs.album_title} - {rs.track_title} ({rs.track_mbid})")
            state.c_youtube_hits += 1

    # If absolutely no match can be found, create a fallback scrobble with just the basic data
    if scrobble is None:
        log.debug("No match, using basic scrobble data.")
        scrobble = ExtendedScrobble.from_basic_data(rs)
        state.c_basic_info_hits += 1

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

    return scrobble


def generate_extended_data(state: State):
    """
    Generate extended scrobble data from the available scrobbles.
    Saves the data into a spreadsheet (location determined by configuration file).

    Args:
        state:
            State instance to read scrobbles and cache from.

            Expected keys already in state:
                - cache_by_album (type: Dict[str, List[LibraryFile])
                - cache_by_artist (type: Dict[str, List[LibraryFile])
                - cache_by_track_title (type: Dict[str, List[LibraryFile])
                - cache_by_track_mbid (type: Dict[str, LibraryFile])
                - scrobbles (type: List[Dict[Any, Any]])

            Appends the following keys to state:
                - youtube_cache_by_query (type: Dict[str, int])
                - local_cache_by_partial_metadata (type: Dict[Tuple[str, str, str], LibraryFile])
                - c_local_mbid_hits (type: int)
                - c_local_metadata_hits (type: int)
                - c_musicbrainz_hits (type: int)
                - c_youtube_hits (type: int)
                - c_basic_info_hits (type: int)
    """
    log.info("[STEP 3] Generating extended data...")
    t_start = time.time()

    scrobbles_len = len(state.scrobbles)

    # Create an openpyxl workbook and the data sheet
    xl_workbook = Workbook()
    sheet = xl_workbook.active
    sheet.title = "Data"


    # Set up search cache
    # This really pays off if the tracks repeat (over a longer period of time for example)
    # TODO implement a better cache than this
    #   cache should probably carry over restarts, but we need a TTL

    # TODO cache setup to a separate function
    # Dict[query, duration] (Dict[str, int])
    state.youtube_cache_by_query = {}
    # Dict[(title, album, artist), LibraryFile]
    state.local_cache_by_partial_metadata = {}

    # Append the header
    sheet.append(ExtendedScrobble.spreadsheet_header())

    # Count different hit types for statistics at the end
    state.c_local_mbid_hits = 0
    state.c_local_metadata_hits = 0
    state.c_musicbrainz_hits = 0
    state.c_youtube_hits = 0
    state.c_basic_info_hits = 0

    c = 0
    # Go through every scrobble and append a row for each entry
    for scrobble_raw_data in state.scrobbles:
        try:
            extended_scrobble: ExtendedScrobble = process_single_scrobble(state, scrobble_raw_data)
        except Exception as e:
            log.warning(f"Failed to process scrobble ({e}): \"{scrobble_raw_data}\"")
        else:
            sheet.append(extended_scrobble.to_spreadsheet_list())

            # Log progress
            c += 1
            if c % config.PARSE_LOG_INTERVAL == 0:
                log.info(f"Parsing progress: {c} scrobbles "
                         f"({round(c / scrobbles_len * 100, 1)}%)")

    # Save the workbook to the configured path
    retries = 0
    written = False

    while retries < 5:
        try:
            xl_workbook.save(filename=config.XLSX_OUTPUT_PATH)
            written = True
            break
        except PermissionError:
            log.warning("PermissionError while trying to open spreadsheet file, retrying in 5 seconds.")
            time.sleep(5)
            retries += 1

    if written is False:
        log.critical(f"Failed to write spreadsheet file to \"{config.XLSX_OUTPUT_PATH}\" after 5 retries.")
        exit(1)

    t_total = round(time.time() - t_start, 1)
    log.info(f"Spreadsheet generated and saved in {t_total}s")
    log.info(f"Spreadsheet location: \"{config.XLSX_OUTPUT_PATH}\"")


def print_end_stats(state: State):
    scrobbles_len = len(state.scrobbles)
    c_local_mbid_hits = state.c_local_mbid_hits
    c_local_metadata_hits = state.c_local_metadata_hits
    c_musicbrainz_hits = state.c_musicbrainz_hits
    c_youtube_hits = state.c_youtube_hits
    c_basic_info_hits = state.c_basic_info_hits

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


def main():
    """
    Main entry point
    """
    # Inhibit Windows system sleep, and uninhibit at the end of the script
    # Silently fails on anything but Windows
    # To make sure this is working on Windows, you can run "powercfg /requests" and look under SYSTEM
    inhibit()

    global_state: State = State("main_state")

    # TODO move logging from specific functions into main?
    ##
    # 1) Load/generate the library cache and scrobbles
    ##
    # ensure_library_cache will fill the above state
    ensure_library_cache(global_state)
    load_scrobbles(global_state)

    ##
    # 2) Generate and save the extended data
    ##
    generate_extended_data(global_state)
    print_end_stats(global_state)

    # Uninhibit Windows system sleep
    uninhibit()


if __name__ == '__main__':
    main()

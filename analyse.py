import logging
from core.configuration import config
logging.basicConfig(level=config.VERBOSITY)

import glob
import traceback
import time
from datetime import datetime
from os import path
from json import load, dump
from typing import Optional, Dict, List, Any, Tuple, Union

from mutagen import File, FileType, MutagenError
from openpyxl import Workbook
from fuzzywuzzy.fuzz import partial_ratio, UQRatio
from fuzzywuzzy.process import extractOne
from youtubesearchpython import SearchVideos

from core.library import LibraryFile
from core.scrobble import ExtendedScrobble, TrackSourceType, RawScrobble
from core.utilities import youtube_length_to_sec, TimedContext, generate_random_filename_safe_text
from core.musicbrainz import ReleaseTrack
from core.genres import fetch_genre_by_metadata
from core.prevent_sleep import inhibit, uninhibit
from core.state import LibraryCacheState, SearchCacheState, StatisticsState, AnalysisState

log = logging.getLogger(__name__)


TypeRawLibraryCache = Dict[
    str,
    Union[
        Dict[str, List[LibraryFile]],
        Dict[str, LibraryFile]
    ]
]


##
# Cache the music library
##
def find_music_library_files(root_dir: str) -> List[str]:
    """
    Given a root directory, build a list of audio file paths.

    Args:
        root_dir:
            Root directory to start in. Includes subdirectories.

    Returns:
        A list of strings contaning audio file paths.
    """
    globs: List[str] = [
        path.join(root_dir, f"**/*.{ext_glob}")
        for ext_glob in ("mp3", "ogg", "wav", "flac", "m4a")
    ]

    files: List[str] = []
    for g in globs:
        files.extend(glob.glob(g, recursive=True))

    files.sort()
    return files


def build_library_metadata_cache(file_list: List[str]) -> TypeRawLibraryCache:
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
            # TODO this currently supports mutagen easy tags, so pretty much only MP3 and MP4 are guaranteed
            #   Look into support for non-easy mutagen tags
            #   (seems like we might only need to map each type's tags with something like a dict?)
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

    log.info(f"Processed {files_successful} audio files ({files_failed} failed).")

    return {
        "cache_by_album": by_album,
        "cache_by_artist": by_artist,
        "cache_by_track_title": by_track_title,
        "cache_by_track_mbid": by_track_mbid,
    }


def load_library_metadata() -> TypeRawLibraryCache:
    """
    Loads the cached version of the music library. The cache is saved in the configurable cache directory.
    Recreates LibraryFile instances from the data.

    Returns:
        A
    """
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


def save_library_metadata(raw_cache: TypeRawLibraryCache) -> None:
    def serialize_libraryfiles_list(full: Dict[str, List[LibraryFile]]) -> Dict[str, List[str]]:
        return {
            k: [lib_f.dump() for lib_f in v] for k, v in full.items()
        }

    def serialize_libraryfiles_single(full: Dict[str, LibraryFile]) -> Dict[str, str]:
        return {
            k: v.dump() for k, v in full.items()
        }

    dumped = {
        "cache_by_album": serialize_libraryfiles_list(raw_cache["cache_by_album"]),
        "cache_by_artist": serialize_libraryfiles_list(raw_cache["cache_by_artist"]),
        "cache_by_track_title": serialize_libraryfiles_list(raw_cache["cache_by_track_title"]),
        "cache_by_track_mbid": serialize_libraryfiles_single(raw_cache["cache_by_track_mbid"]),
    }

    with open(config.LIBRARY_CACHE_FILE, "w", encoding="utf8") as lib_file:
        dump(
            dumped,
            lib_file,
            ensure_ascii=False,
        )


def ensure_library_cache(state: AnalysisState) -> None:
    """
    Makes sure the music library cache exists.
    Generates one if needed, otherwise loads from file.
    Updates passed state with the music library cache.

    Args:
        state:
            AnalysisState instance into which to save the new LocalLibraryCache instance.
            (AnalysisState's library_cache attribute is updated)
    """
    # Build audio metadata cache if needed (otherwise just load the json cache)
    # TODO detect changes in music library!

    # If a cache already exists, load it
    # TODO switch to ignore cache? (deleting the cache file also works for now)
    if path.isfile(config.LIBRARY_CACHE_FILE):
        log.info("Local music library cache found, loading.")
        raw_cache = load_library_metadata()
        log.info("Local music library cache loaded.")
    elif config.LIBRARY_CACHE_FILE not in (None, ""):
        log.info("No cache found, generating.")
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
    # So we separate it into smaller chunks and save each separately into our state

    # This is done with LocalLibraryCache.set_from_raw_cache
    library_state: LibraryCacheState = LibraryCacheState()
    library_state.set_from_raw_cache(raw_cache)

    # Update the AnalysisState's library_cache ref and we're done here!
    state.library_cache = library_state


##
# Scrobbles
##
def load_scrobbles(state: AnalysisState) -> None:
    """
    Load the scrobbles file into JSON and flatten it.
    Updates state with the loaded scrobble data.

    Args:
        state:
            AnalysisState instance to save the scrobbles into.
            (AnalysisState's scrobbles attribute is updated)
    """
    def load_and_flatten(json_file_path: str) -> List:
        with open(json_file_path, "r", encoding="utf8") as scrobbles_file:
            scrobbles_raw = load(scrobbles_file)

        # Flatten scrobble pages into a big list
        flattened = [item for sublist in scrobbles_raw for item in sublist]
        return flattened

    # TODO option to filter scrobbles by date (from, to)
    # Flatten and save into state
    scrobbles = load_and_flatten(config.SCROBBLES_JSON_PATH)
    state.raw_scrobbles = scrobbles

    log.info(f"{len(scrobbles)} scrobbles loaded.")


##
# Extended data
##

# Define search functions
def find_by_mbid(library_cache: LibraryCacheState, raw_scrobble: RawScrobble) -> Optional[ExtendedScrobble]:
    """
    Try to find exact MusicBrainz track ID match in our local music library.

    Args:
        library_cache:
            LibraryCacheState instance.
        raw_scrobble:
            RawScrobble instance.

    Returns:
        If found, an ExtendedScrobble instance formed from the matched library track. Otherwise None.
    """
    library_track = library_cache.cache_by_track_mbid.get(raw_scrobble.track_mbid)

    if library_track is None:
        return None
    else:
        return ExtendedScrobble.from_library_track(raw_scrobble, library_track, TrackSourceType.LOCAL_LIBRARY_MBID)


def find_by_metadata_full_match(
        library_cache: LibraryCacheState, raw_scrobble: RawScrobble
) -> Optional[ExtendedScrobble]:
    """
    Try to find exact metadata match in our local music library.

    Args:
        library_cache:
            LibraryCacheState instance.
        raw_scrobble:
            RawScrobble instance.

    Returns:
        If found, an ExtendedScrobble instance formed from the matched library track. Otherwise None.
    """
    if raw_scrobble.track_title in library_cache.cache_by_track_title:
        # TODO add mixed exact and partial match?
        #   (e.g. exact title and artist match, then partial album)
        #   Maybe separate the track, album and artist stages?
        # First, match by track title, then filter by artist and album if possible
        track_matches: List[LibraryFile] = library_cache.cache_by_track_title[raw_scrobble.track_title]

        if len(track_matches) < 1:
            return None
        elif len(track_matches) == 1:
            return ExtendedScrobble.from_library_track(
                raw_scrobble, track_matches[0], TrackSourceType.LOCAL_LIBRARY_METADATA_EXACT
            )

        # Then: by artist
        track_matches = [m for m in track_matches if m.artist_name == raw_scrobble.artist_name]

        if len(track_matches) < 1:
            return None
        elif len(track_matches) == 1:
            return ExtendedScrobble.from_library_track(
                raw_scrobble, track_matches[0], TrackSourceType.LOCAL_LIBRARY_METADATA_EXACT
            )

        # Lastly: by album
        track_matches = [m for m in track_matches if m.album_name == raw_scrobble.album_title]

        if len(track_matches) < 1:
            return None
        elif len(track_matches) == 1:
            return ExtendedScrobble.from_library_track(
                raw_scrobble, track_matches[0], TrackSourceType.LOCAL_LIBRARY_METADATA_EXACT
            )
        else:
            # Still multiple matches
            # TODO should this even return None?
            #   Multiple matches would indicate duplicate files, so I'm not sure this should even return None,
            #   maybe just return the first match?
            log.warning(f"Multiple matches when trying full metadata match, returning None. "
                        f"(\"{raw_scrobble}\" fully matches these tracks: {track_matches})")
            return None

    return None


def find_by_metadata_partial_match(
        search_cache: SearchCacheState,
        library_cache: LibraryCacheState,
        raw_scrobble: RawScrobble
) -> Optional[ExtendedScrobble]:
    """
    Try to find partial metadata match in our local music library.

    Args:
        search_cache:
            SearchCacheState instance.
        library_cache:
            LibraryCacheState instance.
        raw_scrobble:
            RawScrobble instance.

    Returns:
        If found, an ExtendedScrobble instance formed from the matched library track. Otherwise None.
    """
    # Use cached result if possible
    caching_tuple = (raw_scrobble.track_title, raw_scrobble.album_title, raw_scrobble.artist_name)
    if caching_tuple in search_cache.local_by_partial_metadata:
        log.debug("find_by_metadata_partial_match: cache hit")
        track: Optional[LibraryFile] = search_cache.local_by_partial_metadata[caching_tuple]

        if track is None:
            return None
        else:
            return ExtendedScrobble.from_library_track(
                raw_scrobble, track, TrackSourceType.LOCAL_LIBRARY_METADATA_PARTIAL
            )

    log.debug("find_by_metadata_partial_match: cache miss")
    # Start by filtering to the closest artist name match
    best_artist_match: Optional[Tuple[str, int]] = extractOne(
        raw_scrobble.artist_name,
        library_cache.cache_list_of_artists,
        scorer=UQRatio,
        score_cutoff=config.FUZZY_MIN_ARTIST
    )

    # Edge case: if no match can be found, we should stop
    if best_artist_match is None:
        search_cache.local_by_partial_metadata[caching_tuple] = None
        return None

    # Otherwise, build a list of LibraryFiles for further filtering
    current_cache_list: List[LibraryFile] = library_cache.cache_by_artist[best_artist_match[0]]

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
        search_cache.local_by_partial_metadata[caching_tuple] = None
        return None

    # Otherwise build a ExtendedScrobble with this information
    final_track = current_cache_list[c_to_track_titles.index(best_track_match[0])]

    return ExtendedScrobble.from_library_track(
        raw_scrobble, final_track, TrackSourceType.LOCAL_LIBRARY_METADATA_PARTIAL
    )


def find_on_musicbrainz(raw_scrobble: RawScrobble) -> Optional[ExtendedScrobble]:
    """
    Try to find a track MBID match on MusicBrainz.

    Args:
        raw_scrobble:
            RawScrobble instance.

    Returns:
        If found, an ExtendedScrobble instance formed with the help of MusicBrainz' data.
    """
    release_track = ReleaseTrack.from_track_mbid(raw_scrobble.track_mbid)
    if release_track is None:
        return None

    log.debug(f"find_on_musicbrainz: got release track")
    return ExtendedScrobble.from_musicbrainz_track(raw_scrobble, release_track)


def find_on_youtube(
        search_cache: SearchCacheState,
        raw_scrobble: RawScrobble
) -> Optional[ExtendedScrobble]:
    """
    Try to find a track by metadata on YouTube. Works simply by searching for the string
    "artist album track" and trying to find the best match out of the first 8 results.

    Args:
        search_cache:
            SearchCacheState instance.
        raw_scrobble:
            RawScrobble instance.

    Returns:
        If found, an ExtendedScrobble instance with the length from the matched YouTube video.
    """
    # Search YouTube for the closest "artist title" match
    query = f"{raw_scrobble.artist_name} {raw_scrobble.album_title} {raw_scrobble.track_title}"

    if query in search_cache.youtube_by_query:
        log.debug("find_on_youtube: cache hit")
        duration_sec = search_cache.youtube_by_query[query]
    else:
        log.debug("find_on_youtube: cache miss")
        search = SearchVideos(query, mode="list", max_results=8)

        # Find the closest match
        closest_match = extractOne(
            query,
            search.titles,
            scorer=partial_ratio,
            score_cutoff=config.FUZZY_YOUTUBE_MIN_TITLE
        )

        if closest_match is None:
            log.debug("find_on_youtube: no good match")
            return None
        else:
            log.debug(f"find_on_youtube: got a good match - \"{closest_match[0]}\"")

        # Parse the closest one into a proper ExtendedScrobble
        index = search.titles.index(closest_match[0])
        duration_human = search.durations[index]
        duration_sec = youtube_length_to_sec(duration_human)

        # Store the video length in cache to speed up repeated listens
        search_cache.youtube_by_query[query] = duration_sec

    return ExtendedScrobble.from_youtube(raw_scrobble, duration_sec)


def process_single_scrobble(
        state: AnalysisState,
        raw_data: Dict[Any, Any]
) -> ExtendedScrobble:
    """
    Given raw data about a scrobble event, process it and attempt to find more data about it.
    Queries the local music library, YouTube, MusicBrainz and Last.fm if needed.

    Args:
        state:
            AnalysisState instance.
        raw_data:
            A dictionary with the raw scrobble data.

    Returns:
        An ExtendedScrobble instance. Contains as much data as can be extracted from it.

        Modes of search:
            1) Use track MBID (local library)
            2) Use track metadata (local library) - try exact match first, then partial
            3) Use track MBID (search on MusicBrainz)
            4) Use track metadata (YouTube search)
    """
    ####
    # Load raw scrobble data into a RawScroble instance
    ####
    rs: RawScrobble = RawScrobble.from_raw_data(raw_data)

    # Because lazy string interpolation is hard,
    # we enclose the bigger debug logs in a isEnabledFor
    if log.isEnabledFor(logging.DEBUG):
        log.debug(f"Processing scrobble: {str(rs)} (raw_data=\"{raw_data}\")")

    library_cache: LibraryCacheState = state.library_cache
    search_cache: SearchCacheState = state.search_cache
    stats: StatisticsState = state.statistics

    #########
    # Find source with track length and more accurate metadata
    #########
    # Multiple modes of search, first has highest priority:
    # 1) Use track MBID (local library)
    # 2) Use track metadata (local library) - try exact match first, then partial
    # 3) Use track MBID (search on MusicBrainz)
    # 4) Use track metadata (YouTube search)
    scrobble: Optional[ExtendedScrobble] = None

    # Try exact mbid search (local library)
    if rs.track_mbid is not None:
        # Look up the track in cache via mbid
        scrobble = find_by_mbid(library_cache, rs)
        if scrobble is not None:
            log.debug(f"Match by MBID (local library): {rs}")
            stats.local_mbid_hits += 1

    # Try exact metadata match (local library)
    if scrobble is None and rs.track_title is not None:
        scrobble = find_by_metadata_full_match(library_cache, rs)
        if scrobble is not None:
            log.debug(f"Match by exact metadata (local library): {rs}")
            stats.local_metadata_exact_hits += 1

    # Try partial metadata match (local library)
    if scrobble is None and rs.track_title is not None:
        scrobble = find_by_metadata_partial_match(search_cache, library_cache, rs)
        if scrobble is not None:
            log.debug(f"Match by partial metadata (local library): {rs}")
            stats.local_metadata_partial_hits += 1

    # Try MusicBrainz
    if scrobble is None and rs.track_mbid is not None:
        scrobble = find_on_musicbrainz(rs)
        if scrobble is not None:
            log.debug(f"Match by MBID (MusicBrainz): {rs}")
            stats.musicbrainz_hits += 1

    # Try youtube search
    if scrobble is None:
        scrobble = find_on_youtube(search_cache, rs)
        if scrobble is not None:
            log.debug(f"Match by metadata (YouTube): {rs}")
            stats.youtube_hits += 1

    # If absolutely no match can be found, create a fallback scrobble with just the basic data
    if scrobble is None:
        log.debug("No match, using basic scrobble data.")
        scrobble = ExtendedScrobble.from_basic_data(rs)
        stats.basic_info_hits += 1

    #########
    # Find genre if missing
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


def generate_extended_data(state: AnalysisState):
    """
    Generate extended scrobble data from the available scrobbles.
    Saves the data into a spreadsheet (location determined by configuration file).

    Args:
        state:
            AnalysisState instance to read scrobbles and cache from.
            Expects state.raw_scrobbles to be already loaded.

            Updates the state with
                - statistics (sets the "statistics" key to an instance of StatisticsState) and
                - search cache (YouTube video length / local metadata match cache / ...)
    """
    log.info("Generating extended scrobble data...")
    scrobbles_len = len(state.raw_scrobbles)

    # Create an openpyxl workbook and select the proper sheet
    xl_workbook = Workbook()
    sheet = xl_workbook.active
    sheet.title = "Data"

    # Set up search cache
    # This really pays off if the tracks repeat (over a longer period of time for example)
    # TODO implement a better cache than this
    #   cache should probably carry over restarts, but we need a TTL
    search_cache: SearchCacheState = SearchCacheState()

    # Set up counters for different match types
    # (for statistics at the end)
    stats_state: StatisticsState = StatisticsState()

    # Update the main AnalysisState with the reference to our new stats and cache
    state.statistics = stats_state
    state.search_cache = search_cache

    # Append the spreadsheet header (camel_case names)
    sheet.append(ExtendedScrobble.spreadsheet_header())

    counter = 0
    # Go through every scrobble and append a row for each entry
    for scrobble_raw_data in state.raw_scrobbles:
        try:
            extended_scrobble: ExtendedScrobble = process_single_scrobble(state, scrobble_raw_data)
        except Exception as e:
            # In case of failure, just log and skip the scrobble
            log.warning(f"Failed to process scrobble, skipping ({e}): \"{scrobble_raw_data}\"")
            traceback.print_exc()
        else:
            sheet.append(extended_scrobble.to_spreadsheet_list())

            # Log progress as configured (every parse_log_interval scrobbles)
            counter += 1
            if counter % config.PARSE_LOG_INTERVAL == 0:
                log.info(f"Parsing progress: {counter} scrobbles "
                         f"({round(counter / scrobbles_len * 100, 1)}%)")

    # Save the workbook to the configured path
    # Exponential backoff, starting at 2s
    retries_current_wait = 2
    written = False

    human_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    workbook_output_path = config.XLSX_OUTPUT_PATH.replace(
        "{DATETIME}", human_datetime
    )

    # If the file already exists (which is unlikely, but possible),
    # append a random suffix to the file name
    if path.isfile(workbook_output_path):
        random_suffix: str = generate_random_filename_safe_text(4)
        log.warning(f"Configured spreadsheet output path is \"{workbook_output_path}\", but that file already exists. "
                    f"Appending \"_{random_suffix}\" to the filename.")
        # Tuple[path without extension, ext]
        split_output: Tuple[str, str] = path.splitext(workbook_output_path)

        workbook_output_path = f"{split_output[0]}_{random_suffix}{split_output[1]}"

    # Up to 7 retries (2^7 = 128)
    while retries_current_wait <= 128:
        try:
            xl_workbook.save(filename=workbook_output_path)
            written = True
            break
        except PermissionError:
            log.warning(f"PermissionError while trying to open spreadsheet file, "
                        f"retrying in {retries_current_wait} seconds.")

            time.sleep(retries_current_wait)
            retries_current_wait *= 2

    if written is False:
        log.critical(f"Failed to write spreadsheet file to \"{config.XLSX_OUTPUT_PATH}\".")
        exit(1)


def print_end_stats(state: AnalysisState):
    """
    Log the analysis stats, based on the current state.

    Args:
        state:
            AnalysisState instance to use.
            Expects the "scrobbles" and "statistics" keys to be accurate.
    """
    scrobbles_len = len(state.raw_scrobbles)

    stats = state.statistics

    c_local_mbid = stats.local_mbid_hits
    c_local_metadata_exact = stats.local_metadata_exact_hits
    c_local_metadata_partial = stats.local_metadata_partial_hits
    c_musicbrainz = stats.musicbrainz_hits
    c_youtube = stats.youtube_hits
    c_basic_info = stats.basic_info_hits

    perc_local_mbid = round(c_local_mbid / scrobbles_len * 100, 1)
    perc_local_metadata_exact = round(c_local_metadata_exact / scrobbles_len * 100, 1)
    perc_local_metadata_partial = round(c_local_metadata_partial / scrobbles_len * 100, 1)
    perc_musicbrainz = round(c_musicbrainz / scrobbles_len * 100, 1)
    perc_youtube = round(c_youtube / scrobbles_len * 100, 1)
    perc_basic_info = round(c_basic_info / scrobbles_len * 100, 1)

    log.info(f"Source statistics:\n"
             f"  Local library (MBID): {c_local_mbid} ({perc_local_mbid}%)\n"
             f"  Local library (exact metadata): {c_local_metadata_exact} ({perc_local_metadata_exact}%)\n"
             f"  Local library (partial metadata): {c_local_metadata_partial} ({perc_local_metadata_partial}%)\n"
             f"  MusicBrainz: {c_musicbrainz} ({perc_musicbrainz}%)\n"
             f"  YouTube: {c_youtube} ({perc_youtube}%)\n"
             f"  No matches, just basic data: {c_basic_info} ({perc_basic_info}%)")


def main():
    """
    Main entry point for this script.

    Steps:
        1) If on Windows, makes sure the system won't go to sleep mid-processing
        2) Builds or loads the local music library cache
        3) Loads the scrobbles from file
        4) Generates the extended data and outputs it to a spreadsheet
        5) Shows some quick stats about the quality of lookups
    """
    # Inhibit Windows system sleep, and uninhibit at the end of the script
    # Silently fails on anything but Windows
    # To make sure this is working on Windows, you can run "powercfg /requests" and look under SYSTEM
    inhibit()

    # Our main state
    state: AnalysisState = AnalysisState()

    # TODO move logging from specific functions into main?
    ##
    # 1) Load/generate the library cache and scrobbles
    ##

    # Will fill the state in-place, as will functions down the line
    with TimedContext("Local library cache took {time}s", callback=log.info):
        log.info("Making sure the local music library is cached...")
        ensure_library_cache(state)

    ##
    # Scrobbles
    with TimedContext("Scrobbles file read and parsed in {time}s", callback=log.info):
        log.info("Loading scrobbles...")
        load_scrobbles(state)

    ##
    # 2) Generate and save the extended data
    ##

    ##
    # Generate data
    with TimedContext("Spreadsheet generated and saved in {time}s", callback=log.info):
        generate_extended_data(state)
        log.info(f"Spreadsheet location: \"{config.XLSX_OUTPUT_PATH}\"")

    ##
    # Print statistics
    print_end_stats(state)

    # Uninhibit Windows system sleep
    uninhibit()


if __name__ == '__main__':
    main()

import requests
import os
import logging
import pylast as pyl
from typing import List, Tuple, Optional, Dict, Union, Set, Generator
from yaml import safe_load

from fuzzywuzzy.fuzz import UWRatio
from fuzzywuzzy.process import extractOne

from .configuration import config
from .state import GenreDataState

log = logging.getLogger(__name__)

######
# genres.py
# Genre search is inspied by beets' LastGenre plugin (and actually uses its genre tree).
######

# LastFM-extended-scrobbles uses beetbox/beets' genres tree.
# Licensed under MIT
# Thank you Beets <3
BEETS_GENRES_TREE_SRC = "https://raw.githubusercontent.com/beetbox/beets/master/beetsplug/lastgenre/genres-tree.yaml"
BEETS_GENRES_LIST_SRC = "https://raw.githubusercontent.com/beetbox/beets/master/beetsplug/lastgenre/genres.txt"
BEETS_LICENSE_SRC = "https://raw.githubusercontent.com/beetbox/beets/master/LICENSE"

BEETS_GENRES_TREE_PATH = os.path.join(config.CACHE_DIR, "genres-tree.yaml")
BEETS_GENRES_LIST_PATH = os.path.join(config.CACHE_DIR, "genres.txt")
BEETS_LICENSE_PATH = os.path.join(config.CACHE_DIR, "LICENSE_BEETS_GENRES.md")

PYLAST_CACHING_FILE = os.path.join(config.CACHE_DIR, "pylast_cache")

lastfm = pyl.LastFMNetwork(
    api_key=config.LASTFM_API_KEY,
    api_secret=config.LASTFM_API_SECRET,
)
lastfm.enable_caching(PYLAST_CACHING_FILE)
lastfm.enable_rate_limit()


class Genre:
    # DEPRECATED the genre tree is unused
    __slots__ = ("name", "parent_genre", "is_leaf", "tree_depth")

    def __init__(self, genre_name: str, parent_genre: "Genre", is_leaf: bool, tree_depth: int):
        self.name = genre_name
        self.parent_genre = parent_genre
        self.is_leaf = is_leaf
        self.tree_depth = tree_depth

    def __str__(self):
        return f"<Genre \"{self.name}\" " \
               f"parent=\"{self.parent_genre.name if self.parent_genre is not None else 'None'}\" " \
               f"is_leaf={self.is_leaf} " \
               f"depth={self.tree_depth}>"

    def parents(self) -> List["Genre"]:
        """
        Return a list of parent nodes, ordered from closest to root.

        Returns:
            A list of Genre instances, which are parents of the passed node, ordered from closest to root.
        """
        parents = []

        current: Genre = self.parent_genre
        while current is not None:
            parents.append(current)
            current = current.parent_genre

        return parents


def download_genre_data() -> None:
    """
    Downloads the genre data from beets' GitHub repository. Saves into the configurable cache directory.
    """
    log.info("Downloading genre data...")

    log.debug(f"Downloading genre list from {BEETS_GENRES_LIST_SRC}")
    resp_list = requests.get(BEETS_GENRES_LIST_SRC)
    with open(BEETS_GENRES_LIST_PATH, "wb") as genre_list_f:
        for chunk in resp_list.iter_content(chunk_size=256):
            genre_list_f.write(chunk)

    # DEPRECATED the genre tree is unused
    log.debug(f"Downloading genre tree from {BEETS_GENRES_TREE_SRC}")
    resp_tree = requests.get(BEETS_GENRES_TREE_SRC)
    with open(BEETS_GENRES_TREE_PATH, "wb") as genre_tree_f:
        for chunk in resp_tree.iter_content(chunk_size=256):
            genre_tree_f.write(chunk)

    log.debug(f"Downloading Beets' MIT LICENSE notice from {BEETS_LICENSE_SRC}")
    resp_license = requests.get(BEETS_LICENSE_SRC)
    with open(BEETS_LICENSE_PATH, "wb") as genre_license_f:
        for chunk in resp_license.iter_content(chunk_size=256):
            genre_license_f.write(chunk)

    log.info("Genre data downloaded.")


# def _load_genre_tree(genre_tree_raw: dict, output_list: List[Genre],
#                      _parent_node: Genre = None, _depth: int = 0) -> None:
#     # TODO this is actually not used yet, make this an option
#     #   (allow for most-specific results)
#     # DEPRECATED the genre tree is unused
#     """
#     Generate a list of Genre instances.
#
#     Args:
#         genre_tree_raw:
#             Raw genre tree data.
#         output_list:
#             Due to the nature of lists, this is the list of Genre instances will end up in.
#         _parent_node:
#             Don't use this directly, it is used for recursion. Contains the parent node for the current subtree.
#     """
#     if type(genre_tree_raw) is list:
#         for element in genre_tree_raw:
#             # By checking if we're about to reach the end, we should save some time by directly appending
#             # instead of recursively calling for a simple string
#             if type(element) is str:
#                 # This is always a leaf!
#                 genre_instance = Genre(element, _parent_node, True, _depth)
#                 output_list.append(genre_instance)
#             # Otherwise just recursively call with the subtree
#             elif type(element) is dict:
#                 _load_genre_tree(element, output_list, _parent_node, _depth)
#
#     elif type(genre_tree_raw) is dict:
#         for sub_tree_key in genre_tree_raw.keys():
#             # For each key, instantiate a Genre and pass it down the recursion
#             genre_instance = Genre(sub_tree_key, _parent_node, False, _depth)
#             output_list.append(genre_instance)
#
#             _load_genre_tree(genre_tree_raw[sub_tree_key], output_list, genre_instance, _depth + 1)


def load_genre_data(state: GenreDataState) -> None:
    """
    Load the cached genre data. Updates the GenreDataState instance.

    Args:
        state:
            GenreDataState instance.
    """
    log.info("Loading genre data...")

    with open(BEETS_GENRES_LIST_PATH, "r", encoding="utf8") as genre_list_f:
        genres_list_ = genre_list_f.read().splitlines()

    genres_list_ = [a.title() for a in genres_list_]

    # DEPRECATED the genre tree is unused
    # with open(BEETS_GENRES_TREE_PATH, "r", encoding="utf8") as genre_tree_f:
    #     genres_tree_ = safe_load(genre_tree_f)

    # Flatten the tree into a dictionary
    # list_of_genre_instances: List[Genre] = []
    # _load_genre_tree(genres_tree_, list_of_genre_instances)

    # Create a quick access list with just genre names as strings
    # list_of_genre_names = [a.name for a in list_of_genre_instances]

    log.info("Genre data loaded.")
    # return genres_list_, list_of_genre_instances, list_of_genre_names
    genre_state.full_genre_list = genres_list_


# On startup:
# If needed, download the genres tree & list from beets' GitHub repository
if not os.path.isfile(BEETS_GENRES_LIST_PATH):
    download_genre_data()

# DEPRECATED
# full_genres_list: List[str]
# genres_list: List[Genre]
# genres_name_list: List[str]
# DEPRECATED the genre tree is unused
# full_genres_list, genres_list, genres_name_list = load_genre_data()

# Load the genre data globally
genre_state: GenreDataState = GenreDataState()
load_genre_data(genre_state)

######
# Caching
######
cached_tags: Dict[Tuple[str, str, str], Optional[List[str]]] = {}


# Caching decorator
def cache_tag_results(func):
    """
    This function is a decorator for the fetch_genre_by_mbid/metadata functions.
    Caches the results in cached_tags dictionary to speed up subsequent lookups.
    """
    def wrapper(arg_1, arg_2, arg_3, *rest):
        # Return the cached result if possible
        cache_tuple = (arg_1, arg_2, arg_3)
        if cache_tuple in cached_tags:
            log.debug(f"{func.__name__}: cache hit")
            return cached_tags[cache_tuple]

        # Otherwise call the function and cache its result
        log.debug(f"{func.__name__}: cache miss")
        result = func(arg_1, arg_2, arg_3, *rest)
        cached_tags[cache_tuple] = result
        return result

    return wrapper


# def _get_tag_depth(tag: str) -> int:
#     # DEPRECATED this function was meant for the genre tree system, but is unused
#     if tag not in genres_name_list:
#         return -1
#
#     return genres_list[genres_name_list.index(tag)].tree_depth


def _filter_top_tags(tag_list: List[pyl.TopItem]) -> List[str]:
    """
    Given a list of pylast.TopItem tags, filter them by min_genre_weight, deduplicate them and sort them by weight.
    Keeps only valid genres.

    Args:
        tag_list:
            A list of pylast.TopItem tags.

    Returns:
        Sorted and deduplicated list of genre names.
    """
    # Now we merge and filter the tags
    # noinspection PyUnresolvedReferences
    merged_tags: List[Tuple[str, int]] = [
        (a.item.name, int(a.weight)) for a in
        tag_list
        if int(a.weight) > config.MIN_TAG_WEIGHT
    ]

    # Sort by popularity and deduplicate
    sorted_tags_str: Set[str] = set([a[0] for a in sorted(merged_tags, key=lambda e: e[1])])
    # Now filter with the genre whitelist
    filtered_tags: List[str] = [
        tag.title() for tag in list(sorted_tags_str) if tag.title() in genre_state.full_genre_list
    ]
    # Shorten the list to max_genre_count (see config.toml)
    return filtered_tags[:config.MAX_GENRE_COUNT]


def _parse_lastfm_track_genre(
        track: Optional[pyl.Track],
        album: Optional[pyl.Album],
        artist: pyl.Artist,
) -> List[str]:
    """
    Extract genre tags from Last.fm's tag system.

    Args:
        track:
            pylast.Track instance to search for tags on
        album:
            pylast.Album instance to search for tags on
        artist:
            pylast.Artist instance to search for tags on

    Returns:
        List of strings, representing the best choices for genres.
        Length depends on max_genre_count config value.
    """
    # Uses the most accurate genres
    # Tries the track first, then the album, then finally the artist if we still don't have enough genres
    # If enough tags are in the track and album, the artist tags are not even downloaded.
    final_tag_list: List[str] = []

    if track is not None:
        track_tags_raw: List[pyl.TopItem] = track.get_top_tags(limit=config.MAX_GENRE_COUNT)
        track_tags: List[str] = _filter_top_tags(track_tags_raw)
        final_tag_list += track_tags

    if album is not None and len(final_tag_list) < config.MAX_GENRE_COUNT:
        album_tags_raw: List[pyl.TopItem] = album.get_top_tags(limit=config.MAX_GENRE_COUNT)
        album_tags: List[str] = _filter_top_tags(album_tags_raw)
        final_tag_list += album_tags

    if len(final_tag_list) < config.MAX_GENRE_COUNT:
        artist_tags_raw: List[pyl.TopItem] = artist.get_top_tags(limit=config.MAX_GENRE_COUNT)
        artist_tags: List[str] = _filter_top_tags(artist_tags_raw)
        final_tag_list += artist_tags

    return final_tag_list[:config.MAX_GENRE_COUNT]


def _search_page_gen(
        pylast_search: Union[pyl.AlbumSearch, pyl.TrackSearch, pyl.ArtistSearch],
        page_limit: int = config.MAX_LASTFM_PAGES
) -> Generator[List[Union[pyl.Album, pyl.Track, pyl.Artist]], None, None]:
    """
    Fetch results from a pylast AlbumSearch/TrackSearch/ArtistSearch object.

    Args:
        pylast_search:
            pylast.*Search object to fetch pages for
        page_limit:
            Hard page limit.

    Returns:
        A generator, returns next page (list) of corresponding pylast results
        (pylast.Album for pylast.AlbumSearch, ...) on each yield.
    """
    counter = 0
    last = pylast_search.get_next_page()
    while len(last) > 0 and counter < page_limit:
        counter += 1
        yield pylast_search.get_next_page()


@cache_tag_results
def fetch_genre_by_mbid(track_mbid: str, album_mbid: str, artist_mbid: str) -> Optional[List[str]]:
    """
    Given a track, album and artist MBID, find the corresponding Last.fm entries.
    This function is cached using a combination of all three arguments.

    Args:
        track_mbid:
            String with the track's MBID.
        album_mbid:
            String with the album's MBID.
        artist_mbid:
            String with the artist's MBID.

    Returns:
        List of strings containing title-cased genre names.
        None if no result.
    """
    try:
        track: pyl.Track = lastfm.get_track_by_mbid(track_mbid)
        album: pyl.Album = lastfm.get_album_by_mbid(album_mbid)
        artist: pyl.Artist = lastfm.get_artist_by_mbid(artist_mbid)

        return _parse_lastfm_track_genre(track, album, artist)
    except pyl.WSError:
        # No result
        return None


@cache_tag_results
def fetch_genre_by_metadata(track_title: str, album_title: str, artist_name: str) -> Optional[List[str]]:
    """
    Given a track, album and artist name, find the corresponding Last.fm entries.
    This function is cached using a combination of all three arguments.

    Args:
        track_title:
            String with the track's title.
        album_title:
            String with the album's title.
        artist_name:
            String with the artist's name.

    Returns:
        List of strings containing title-cased genre names.
        None if no result.
    """
    try:
        # Fetch just one page, we don't need more
        # TODO can this cause problems when an artist has multiple tracks with the same title?
        #   Can we even solve this - pylast.Track has no album data?

        track: Optional[pyl.Track] = None
        if track_title is not None and len(track_title) > 0:
            try:
                track_search: List[pyl.Track] = lastfm.search_for_track(artist_name, track_title).get_next_page()
                track_search_list: List[str] = [a.title for a in track_search]
                best_track_extr: Optional[Tuple[str, int]] = extractOne(
                    track_title,
                    track_search_list,
                    scorer=UWRatio,
                    score_cutoff=config.MIN_LASTFM_SIMILARITY
                )
                track: Optional[pyl.Track] = track_search[track_search_list.index(best_track_extr[0])]
            except (pyl.WSError, IndexError, TypeError):
                pass

        # Fetch as many album pages as needed
        album: Optional[pyl.Album] = None
        if album_title is not None and len(album_title) > 0:
            try:
                for album_current_page in _search_page_gen(lastfm.search_for_album(album_title)):
                    album_current_list: List[str] = [a.title for a in album_current_page]
                    best_album_extr: Optional[Tuple[str, int]] = extractOne(
                        album_title,
                        album_current_list,
                        scorer=UWRatio,
                        score_cutoff=config.MIN_LASTFM_SIMILARITY
                    )

                    if best_album_extr is not None:
                        album = album_current_page[album_current_list.index(best_album_extr[0])]
                        break
            except (pyl.WSError, IndexError, TypeError):
                pass

        artist_search: List[pyl.Artist] = lastfm.search_for_artist(artist_name).get_next_page()
        # We might be able to search for genres using only the artist, but if the artist is unavailable
        # the accuracy is usually pretty bad
        if len(artist_search) < 1:
            return None
        artist: pyl.Artist = artist_search[0]

        return _parse_lastfm_track_genre(track, album, artist)
    except (pyl.WSError, IndexError):
        # No result
        return None

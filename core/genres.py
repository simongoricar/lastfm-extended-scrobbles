import requests
import os
import logging
import pylast as pyl
from typing import List, Tuple, Optional, Dict, Union, Set
from yaml import safe_load

from fuzzywuzzy.fuzz import UWRatio
from fuzzywuzzy.process import extractOne

from .configuration import config

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
    log.info("Downloading genre data...")

    log.debug(f"Downloading genre list from {BEETS_GENRES_LIST_SRC}")
    resp_list = requests.get(BEETS_GENRES_LIST_SRC)
    with open(BEETS_GENRES_LIST_PATH, "wb") as genre_list_f:
        for chunk in resp_list.iter_content(chunk_size=256):
            genre_list_f.write(chunk)

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


def _load_genre_tree(genre_tree_raw: dict, output_list: List[Genre],
                     _parent_node: Genre = None, _depth: int = 0) -> None:
    # TODO this is actually not used yet, make this an option
    # (allow for most-specific results)
    """
    Generate a list of Genre instances.

    Args:
        genre_tree_raw:
            Raw genre tree data.
        output_list:
            Due to the nature of lists, this is the list of Genre instances will end up in.
        _parent_node:
            Don't use this directly, it is used for recursion. Contains the parent node for the current subtree.
    """
    if type(genre_tree_raw) is list:
        for element in genre_tree_raw:
            # By checking if we're about to reach the end, we should save some time by directly appending
            # instead of recursively calling for a simple string
            if type(element) is str:
                # This is always a leaf!
                genre_instance = Genre(element, _parent_node, True, _depth)
                output_list.append(genre_instance)
            # Otherwise just recursively call with the subtree
            elif type(element) is dict:
                _load_genre_tree(element, output_list, _parent_node, _depth)

    elif type(genre_tree_raw) is dict:
        for sub_tree_key in genre_tree_raw.keys():
            # For each key, instantiate a Genre and pass it down the recursion
            genre_instance = Genre(sub_tree_key, _parent_node, False, _depth)
            output_list.append(genre_instance)

            _load_genre_tree(genre_tree_raw[sub_tree_key], output_list, genre_instance, _depth + 1)


def load_genre_data() -> Tuple[List[str], List[Genre], List[str]]:
    log.info("Loading genre data...")

    with open(BEETS_GENRES_LIST_PATH, "r", encoding="utf8") as genre_list_f:
        genres_list_ = genre_list_f.read().splitlines()

    genres_list_ = [a.title() for a in genres_list_]

    with open(BEETS_GENRES_TREE_PATH, "r", encoding="utf8") as genre_tree_f:
        genres_tree_ = safe_load(genre_tree_f)

    # Flatten the tree into a dictionary
    list_of_genre_instances: List[Genre] = []
    _load_genre_tree(genres_tree_, list_of_genre_instances)

    # Create a quick access list with just genre names as strings
    list_of_genre_names = [a.name for a in list_of_genre_instances]

    log.info("Genre data loaded.")
    return genres_list_, list_of_genre_instances, list_of_genre_names


# On startup:
# If needed, download the genres tree & list from beets' GitHub repository
if not os.path.isfile(BEETS_GENRES_LIST_PATH) or not os.path.isfile(BEETS_GENRES_TREE_PATH):
    download_genre_data()

# Load the genre data globally
full_genres_list: List[str]
genres_list: List[Genre]
genres_name_list: List[str]

full_genres_list, genres_list, genres_name_list = load_genre_data()

######
# Caching
######
cached_tags: Dict[Tuple[str, str, str], Optional[List[str]]] = {}


def _get_tag_depth(tag: str) -> int:
    if tag not in genres_name_list:
        return -1

    return genres_list[genres_name_list.index(tag)].tree_depth


def _parse_lastfm_track_genre(
        track: pyl.Track,
        album: pyl.Album,
        artist: pyl.Artist,
) -> List[str]:
    """
    Extract genre tags from Last.fm's tag system.

    Args:
        track:
            pylast Track instance to search for tags on
        album:
            pylast Album instance to search for tags on
        artist:
            pylast Artist instance to search for tags on

    Returns:
        List of strings, representing the best choices for genres.
        Length depends on max_genre_count config value.
    """
    track_tags: List[pyl.TopItem] = track.get_top_tags(limit=config.MAX_GENRE_COUNT)
    album_tags: List[pyl.TopItem] = album.get_top_tags(limit=config.MAX_GENRE_COUNT)
    artist_tags: List[pyl.Artist] = artist.get_top_tags(limit=config.MAX_GENRE_COUNT)

    # Now we merge and filter the tags
    # noinspection PyUnresolvedReferences
    merged_tags: List[Tuple[str, int]] = [
        (a.item.name, int(a.weight)) for a in
        track_tags + album_tags + artist_tags
        if int(a.weight) > config.MIN_GENRE_WEIGHT
    ]

    # Sort by popularity and deduplicate
    sorted_tags_str: Set[str] = set([a[0] for a in sorted(merged_tags, key=lambda e: e[1])])
    # Now filter with the genre whitelist
    filtered_tags: List[str] = [
        tag.title() for tag in list(sorted_tags_str) if tag.title() in full_genres_list
    ]
    # Shorten the list to max_genre_count (see config.toml)
    final_tags: List[str] = filtered_tags[:config.MAX_GENRE_COUNT]

    return final_tags


def _fetch_all_pages(
        pylast_search: Union[pyl.AlbumSearch, pyl.TrackSearch, pyl.ArtistSearch],
        page_limit: int = 15
) -> List[Union[pyl.Album, pyl.Track, pyl.Artist]]:
    """
    Fetch all results from a pylast AlbumSearch/TrackSearch/ArtistSearch object.

    Args:
        pylast_search:
            pylast search object to fetch pages for
        page_limit:
            Hard page limit.

    Returns:
        List of corresponding pylast results (pylast.Album for pylast.AlbumSearch, ...)
    """
    total = []

    counter = 0
    last = pylast_search.get_next_page()
    while len(last) > 0 and counter < page_limit:
        total += last

        counter += 1
        last = pylast_search.get_next_page()

    return total


def fetch_genre_by_mbid(track_mbid: str, album_mbid: str, artist_mbid: str) -> Optional[List[str]]:
    cache_tuple = (track_mbid, album_mbid, artist_mbid)
    if cache_tuple in cached_tags:
        log.debug("fetch_genre_by_mbid: cache hit")
        return cached_tags[cache_tuple]

    log.debug("fetch_genre_by_mbid: cache miss")

    try:
        track: pyl.Track = lastfm.get_track_by_mbid(track_mbid)
        album: pyl.Album = lastfm.get_album_by_mbid(album_mbid)
        artist: pyl.Artist = lastfm.get_artist_by_mbid(artist_mbid)

        result = _parse_lastfm_track_genre(track, album, artist)
        cached_tags[cache_tuple] = result
        return result
    except pyl.WSError:
        # No result
        cached_tags[cache_tuple] = None
        return None


def fetch_genre_by_metatada(track_title: str, album_title: str, artist_name: str) -> Optional[List[str]]:
    # TODO convert this caching method to a decorator
    cache_tuple = (track_title, album_title, artist_name)
    if cache_tuple in cached_tags:
        log.debug("fetch_genre_by_metadata: cache hit")
        return cached_tags[cache_tuple]

    log.debug("fetch_genre_by_metadata: cache miss")

    try:
        track_search: List[pyl.Track] = _fetch_all_pages(lastfm.search_for_track(artist_name, track_title))
        album_search: List[pyl.Album] = _fetch_all_pages(lastfm.search_for_album(album_title))
        artist_search: List[pyl.Artist] = _fetch_all_pages(lastfm.search_for_artist(artist_name))

        if len(track_search) < 1:
            cached_tags[cache_tuple] = None
            return None

        track: pyl.Track = track_search[0]

        # Choose best matching album
        _title_list: List[str] = [a.title for a in album_search]
        best_album_extr: Optional[Tuple[str, int]] = extractOne(
            album_title,
            _title_list,
            scorer=UWRatio,
            score_cutoff=config.MIN_LASTFM_SIMILARITY
        )
        if best_album_extr is None:
            cached_tags[cache_tuple] = None
            return None

        album: pyl.Album = album_search[_title_list.index(best_album_extr[0])]

        # Preprocesssed by Last.fm already, the first result should be the best match
        artist: pyl.Artist = artist_search[0]

        result = _parse_lastfm_track_genre(track, album, artist)
        cached_tags[cache_tuple] = result
        return result
    except (pyl.WSError, IndexError):
        # No result
        cached_tags[cache_tuple] = None
        return None


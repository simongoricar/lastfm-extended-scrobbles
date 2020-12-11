from typing import Dict, List, Union, Tuple, Any, Optional

from .library import LibraryFile


# class SingletonByName(type):
#     _by_name: Dict[str, "State"] = {}
#
#     def __call__(cls, name: str, *args, **kwargs):
#         if name in cls._by_name:
#             # Return existing instance
#             return cls._by_name[name]
#         else:
#             # Make new instance
#             instance = super(SingletonByName, cls).__call__(name, *args, **kwargs)
#             cls._by_name[name] = instance
#             return instance


# class State(dict, metaclass=SingletonByName):
class State(dict):
    """
    A singleton-by-name dict-like state. First argument is the state name.

    If a State with a specific name was already instantiated, its instance will
    be returned (instead of making a new instance).

    Supports "instance.key = value" assignments.

    This is usually subclassed, see LibraryCacheState for an example.
    """
#    def __init__(self, _name: str, *args, **kwargs):
    def __init__(self, *args, **kwargs):
        super(State, self).__init__(*args, **kwargs)

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, item):
        del self[item]

    def __getattr__(self, item):
        return self[item]


class LibraryCacheState(State):
    """
    Local library cache, contains caching dictionaries and lists.
    """
    __slots__ = (
        "cache_by_album",
        "cache_by_artist",
        "cache_by_track_title",
        "cache_by_track_mbid",
        "cache_list_of_albums",
        "cache_list_of_artists",
        "cache_list_of_tracks",
    )

    def __init__(self):
        super(LibraryCacheState, self).__init__()

        self.cache_by_album: Dict[str, List[LibraryFile]] = {}
        self.cache_by_artist: Dict[str, List[LibraryFile]] = {}
        self.cache_by_track_title: Dict[str, List[LibraryFile]] = {}
        self.cache_by_track_mbid: Dict[str, LibraryFile] = {}

        self.cache_list_of_albums: List[str] = []
        self.cache_list_of_artists: List[str] = []
        self.cache_list_of_tracks: List[str] = []

    def set_from_raw_cache(
            self,
            # phew
            raw_cache: Dict[
                str,
                Union[
                    Dict[str, List[LibraryFile]],
                    Dict[str, LibraryFile]
                ]
            ]
    ):
        """
        Updates the cache based on the passed raw cache.

        Args:
            raw_cache:
                Dictionary of dictionaries, expected keys:
                    - cache_by_album (type: Dict[str, List[LibraryFile]])
                    - cache_by_artist (type: Dict[str, List[LibraryFile]])
                    - cache_by_track_title (type: Dict[str, List[LibraryFile]])
                    - cache_by_track_mbid (type: Dict[str, LibraryFile])
        """
        self.cache_by_album = raw_cache["cache_by_album"]
        self.cache_by_artist = raw_cache["cache_by_artist"]
        self.cache_by_track_title = raw_cache["cache_by_track_title"]
        self.cache_by_track_mbid = raw_cache["cache_by_track_mbid"]

        self.cache_list_of_albums = [str(a) for a in self.cache_by_album.keys()]
        self.cache_list_of_artists = [str(a) for a in self.cache_by_artist.keys()]
        self.cache_list_of_tracks = [str(a) for a in self.cache_by_track_title.keys()]


class SearchCacheState(State):
    """
    Contains the YouTube and other hit cache.
    """
    __slots__ = (
        "youtube_by_query",
        "local_by_partial_metadata",
    )

    def __init__(self):
        super(SearchCacheState, self).__init__()

        self.youtube_by_query: Dict[str, int] = {}
        self.local_by_partial_metadata: Dict[Tuple[str, str, str], Optional[LibraryFile]] = {}


class StatisticsState(State):
    """
    Houses the varous stats counters related to types of scrobble matches.
    """
    __slots__ = (
        "local_mbid_hits",
        "local_metadata_exact_hits",
        "local_metadata_partial_hits",
        "musicbrainz_hits",
        "youtube_hits",
        "basic_info_hits"
    )

    def __init__(self):
        super(StatisticsState, self).__init__()

        self.local_mbid_hits: int = 0
        self.local_metadata_exact_hits: int = 0
        self.local_metadata_partial_hits: int = 0
        self.musicbrainz_hits: int = 0
        self.youtube_hits: int = 0
        self.basic_info_hits: int = 0


class AnalysisState(State):
    """
    "Main" state, contains general information.
    """
    # TODO
    __slots__ = (
        "library_cache",
        "search_cache",
        "raw_scrobbles",
        "statistics",
    )

    def __init__(self):
        super(AnalysisState, self).__init__()

        self.library_cache: Optional[LibraryCacheState] = None
        self.search_cache: Optional[SearchCacheState] = None
        self.raw_scrobbles: List[Dict[Any, Any]] = []
        self.statistics: Optional[StatisticsState] = None

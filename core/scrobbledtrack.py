from typing import Optional, Dict, Any

from .library import LibraryFile


class TrackSourceType:
    LOCAL_LIBRARY = "local_library"
    YOUTUBE = "youtube"


class Scrobble:
    __slots__ = (
        "epoch_time",
        "artist_name",
        "artist_mbid",
        "album_name",
        "album_mbid",
        "track_title",
        "track_mbid",
        "track_source",
        "track_length"
    )

    def __init__(self, **kwargs):
        self.track_source = kwargs.pop("track_source")
        self.epoch_time = kwargs.pop("epoch_time")

        self.artist_name: Optional[str] = kwargs.get("artist_name")
        self.artist_mbid: Optional[str] = kwargs.get("artist_mbid")

        self.album_name: Optional[str] = kwargs.get("album_name")
        self.album_mbid: Optional[str] = kwargs.get("album_mbid")

        self.track_title: Optional[str] = kwargs.get("track_title")
        self.track_mbid: Optional[str] = kwargs.get("track_mbid")
        # Unit: seconds
        self.track_length: Optional[int] = kwargs.get("track_length")

    @classmethod
    def from_library_track(cls, raw_scrobble: Dict[str, Any], track: LibraryFile):
        date_raw = raw_scrobble.get("date")
        scrobble_time = int(date_raw.get("uts"))

        return cls(
            track_source=TrackSourceType.LOCAL_LIBRARY,
            epoch_time=scrobble_time,

            artist_name=track.artist_name,
            artist_mbid=track.artist_mbid,

            album_name=track.album_name,
            album_mbid=track.album_mbid,

            track_title=track.track_title,
            track_mbid=track.track_mbid,
            track_length=track.track_length,
        )

    @classmethod
    def from_youtube(cls):
        pass

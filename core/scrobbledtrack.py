from typing import Optional

from mutagen import FileType


class TrackSourceType:
    LOCAL_LIBRARY = "local_library"
    YOUTUBE = "youtube"


class Scrobble:
    __slots__ = (
        "track_source",
        "epoch_time",
        "artist_name",
        "artist_mbid",
        "album_name",
        "album_mbid",
        "track_title",
        "track_mbid",
    )

    def __init__(self, **kwargs):
        self.track_source = kwargs.pop("track_source")
        self.epoch_time = kwargs.pop("epoch_time")

        self.artist_name: str = kwargs.pop("artist_name", default=None)
        self.artist_mbid: Optional[str] = kwargs.pop("artist_mbid", default=None)

        self.album_name: str = kwargs.pop("album_name", default=None)
        self.album_mbid: Optional[str] = kwargs.pop("album_mbid", default=None)

        self.track_title: str = kwargs.pop("track_title", default=None)
        self.track_mbid: Optional[str] = kwargs.pop("track_mbid", default=None)

    @classmethod
    def from_mutagen(cls, file: FileType):


        return cls(
            track_source=TrackSourceType.LOCAL_LIBRARY,
            # epoch_time=
        )

    @classmethod
    def from_youtube(cls):
        pass

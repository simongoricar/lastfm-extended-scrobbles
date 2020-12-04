from typing import Optional, Dict, Any

from .library import LibraryFile


class TrackSourceType:
    LOCAL_LIBRARY = "local_library"
    YOUTUBE = "youtube"


class Scrobble:
    """
    Extended scrobble data (more so than general last.fm data)
    """
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
    def from_youtube(cls, raw_scrobble: Dict[str, Any], video_duration: int, ):
        date_raw = raw_scrobble.get("date")
        if date_raw is not None:
            scrobble_time = int(date_raw.get("uts"))
        else:
            scrobble_time = None

        # Fall back to title, artist and album of the scrobble
        artist_raw = raw_scrobble.get("artist")
        if artist_raw is not None:
            artist_name = artist_raw.get("#text")
            artist_mbid = artist_raw.get("mbid")
        else:
            # TODO maybe fall back to the youtube video uploader?
            artist_name = None
            artist_mbid = None

        album_raw = raw_scrobble.get("album")
        if album_raw is not None:
            album_name = album_raw.get("#text")
            album_mbid = album_raw.get("mbid")
        else:
            album_name = None
            album_mbid = None

        track_title = raw_scrobble.get("title")
        track_mbid = raw_scrobble.get("mbid")
        # Use length from the video
        track_length = video_duration


        return cls(
            track_source=TrackSourceType.YOUTUBE,
            epoch_time=scrobble_time,

            artist_name=artist_name,
            artist_mbid=artist_mbid,

            album_name=album_name,
            album_mbid=album_mbid,

            track_title=track_title,
            track_mbid=track_mbid,
            track_length=track_length,
        )

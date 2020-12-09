from typing import Optional, Dict, Any, List

from .utilities import get_best_attribute
from .library import LibraryFile
from .musicbrainz import ReleaseTrack


class TrackSourceType:
    JUST_SCROBBLE = "just_scrobble_data"
    LOCAL_LIBRARY_MBID = "local_library_mbid"
    LOCAL_LIBRARY_METADATA = "local_library_metadata"
    MUSICBRAINZ = "musicbrainz"
    YOUTUBE = "youtube"


class RawScrobble:
    """
    Just the original scrobble data.
    """
    __slots__ = (
        "artist_name",
        "artist_mbid",
        "album_title",
        "album_mbid",
        "track_title",
        "track_mbid",
        "track_love",
        "scrobble_time",
    )

    def __init__(self, **kwargs):
        self.artist_name = kwargs.pop("artist_name")
        self.artist_mbid = kwargs.pop("artist_mbid")

        self.album_title = kwargs.pop("album_title")
        self.album_mbid = kwargs.pop("album_mbid")

        self.track_title = kwargs.pop("track_title")
        self.track_mbid = kwargs.pop("track_mbid")
        self.track_love = kwargs.pop("track_love")

        self.scrobble_time = kwargs.pop("scrobble_time")

    @classmethod
    def from_raw_data(cls, data: Dict[str, Any]):
        s_artist_raw: dict = data.get("artist") or {}
        s_album_raw: dict = data.get("album") or {}
        s_date_raw: dict = data.get("date") or {}

        s_artist_mbid: str = s_artist_raw.get("mbid")
        s_artist_name: str = get_best_attribute(s_artist_raw, ("name", "#text"))

        s_album_mbid: str = s_album_raw.get("mbid")
        s_album_title: str = get_best_attribute(s_album_raw, ("name", "#text"))

        s_track_mbid: str = data.get("mbid")
        s_track_title: str = data.get("name")
        s_track_love: bool = True if int(data.get("loved")) == 1 else False

        scrobble_time: Optional[int]
        if s_date_raw:
            scrobble_time = int(s_date_raw.get("uts"))
        else:
            scrobble_time = None

        return cls(
            artist_name=s_artist_name,
            artist_mbid=s_artist_mbid,

            album_title=s_album_title,
            album_mbid=s_album_mbid,

            track_title=s_track_title,
            track_mbid=s_track_mbid,
            track_love=s_track_love,

            scrobble_time=scrobble_time
        )

    def __str__(self):
        return f"<RawScrobble artist=\"{self.artist_name}\" album=\"{self.album_title}\" track=\"{self.track_title}\">"


class Scrobble:
    """
    Extended scrobble data class (more so than general last.fm data).
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
        "track_length",
        "track_loved",
        "genre_list",
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
        track_loved = kwargs.get("track_loved")
        self.track_loved: Optional[int] = int(track_loved) if track_loved is not None else None

        self.genre_list: Optional[List[str]] = kwargs.get("genre_list")

    @classmethod
    def from_library_track(
            cls, raw_scrobble: RawScrobble, track: LibraryFile,
            track_source: str = TrackSourceType.LOCAL_LIBRARY_MBID
    ):
        """
        Use local library track and construct a Scrobble instance with the help of normal scrobble data.

        Args:
            raw_scrobble:
                Raw scrobble dict (one entry) as exported from last.fm.
            track:
                LibraryFile track from the local library.
            track_source:
                TrackSourceType that represents the track source (local music library, MusicBrainz, YouTube, ...)

        Returns:
            Scrobble instance constructed using scrobble data + local music slibrary.
        """
        return cls(
            track_source=track_source,
            epoch_time=raw_scrobble.scrobble_time,

            artist_name=track.artist_name,
            artist_mbid=track.artist_mbid,

            album_name=track.album_name,
            album_mbid=track.album_mbid,

            track_title=track.track_title,
            track_mbid=track.track_mbid,
            track_length=round(track.track_length, 1),
            track_loved=raw_scrobble.track_love,

            genre_list=track.genre_list,
        )

    @classmethod
    def from_musicbrainz_track(cls, raw_scrobble: RawScrobble, track: ReleaseTrack):
        """
        Use MusicBrainz track duration and construct a Scrobble with the help of normal scrobble data.
        Args:
            raw_scrobble:
            track:

        Returns:

        """
        # Use length from ReleaseTrack
        track_length = track.track_length

        return cls(
            track_source=TrackSourceType.MUSICBRAINZ,
            epoch_time=raw_scrobble.scrobble_time,

            artist_name=raw_scrobble.artist_name,
            artist_mbid=raw_scrobble.artist_mbid,

            album_name=raw_scrobble.album_title,
            album_mbid=raw_scrobble.album_mbid,

            track_title=raw_scrobble.track_title,
            track_mbid=raw_scrobble.track_mbid,
            track_length=track_length,
            track_loved=raw_scrobble.track_love,

            genre_list=None,
        )

    @classmethod
    def from_youtube(cls, raw_scrobble: RawScrobble, video_duration: int):
        """
        Use YouTube video duration and construct a Scrobble with the help of normal scrobble data.

        Args:
            raw_scrobble:
                Raw scrobble dict (one entry) as exported from last.fm.
            video_duration:
                YouTube video duration in seconds.

        Returns:
            Scrobble instance constructed using scrobble data + YouTube data.
        """
        # Use length from the video
        track_length = video_duration

        return cls(
            track_source=TrackSourceType.YOUTUBE,
            epoch_time=raw_scrobble.scrobble_time,

            artist_name=raw_scrobble.artist_name,
            artist_mbid=raw_scrobble.artist_mbid,

            album_name=raw_scrobble.album_title,
            album_mbid=raw_scrobble.album_mbid,

            track_title=raw_scrobble.track_title,
            track_mbid=raw_scrobble.track_mbid,
            track_length=track_length,
            track_loved=raw_scrobble.track_love,

            genre_list=None,
        )

    @classmethod
    def from_basic_data(cls, raw_scrobble: RawScrobble):
        """
        Use just basic scrobble data and instance a Scrobble. Length, for example, will be empty though.

        Args:
            raw_scrobble:
                Raw scrobble dict (one entry) as exported from last.fm.

        Returns:
            Scrobble instance constructed only scrobble data.
        """
        return cls(
            track_source=TrackSourceType.JUST_SCROBBLE,
            epoch_time=raw_scrobble.scrobble_time,

            artist_name=raw_scrobble.artist_name,
            artist_mbid=raw_scrobble.artist_mbid,

            album_name=raw_scrobble.album_title,
            album_mbid=raw_scrobble.album_mbid,

            track_title=raw_scrobble.track_title,
            track_mbid=raw_scrobble.track_mbid,
            track_length=None,
            track_loved=raw_scrobble.track_love,

            genre_list=None,
        )

    ########################
    # Spreadsheet formatter
    ########################
    @staticmethod
    def spreadsheet_header() -> list:
        """
        Returns:
            The header for other spredsheet columns.
        """
        return [
            "track_source",
            "scrobble_time",
            "artist_name",
            "artist_mbid",
            "album_title",
            "album_mbid",
            "track_title",
            "track_mbid",
            "track_length",
            "track_loved",
            "genres",
        ]

    def to_spreadsheet_list(self) -> list:
        """
        Converts the current Scrobble to a list representation. Order is the same as spreadsheet_header().

        Returns:
            A list of values from this instance.
        """
        return [
            self.track_source,
            self.epoch_time,
            self.artist_name,
            self.artist_mbid,
            self.album_name,
            self.album_mbid,
            self.track_title,
            self.track_mbid,
            self.track_length,
            self.track_loved,
            ", ".join(self.genre_list if self.genre_list is not None else [])
        ]

from typing import Optional, Dict, Any

from .library import LibraryFile
from .musicbrainz import ReleaseTrack


class TrackSourceType:
    JUST_SCROBBLE = "just_scrobble_data"
    LOCAL_LIBRARY_MBID = "local_library_mbid"
    LOCAL_LIBRARY_METADATA = "local_library_metadata"
    MUSICBRAINZ = "musicbrainz"
    YOUTUBE = "youtube"


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

    @staticmethod
    def parse_raw_scrobble(raw_scrobble: Dict[str, Any]) -> Dict[str, Any]:
        """
        Helper function to parse useful data out of the raw scrobble data.

        Args:
            raw_scrobble:
                Raw scrobble dict (one entry) as exported from last.fm.

        Returns:
            Dict of useful information from the scrobble.
            Keys: time, artist_name, artist_mbid, album_name, album_mbid, track_title, track_mbid
        """
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
            artist_name = None
            artist_mbid = None

        album_raw = raw_scrobble.get("album")
        if album_raw is not None:
            album_name = album_raw.get("#text")
            album_mbid = album_raw.get("mbid")
        else:
            album_name = None
            album_mbid = None

        track_title = raw_scrobble.get("name")
        track_mbid = raw_scrobble.get("mbid")

        return {
            "time": scrobble_time,
            "artist_name": artist_name,
            "artist_mbid": artist_mbid,
            "album_name": album_name,
            "album_mbid": album_mbid,
            "track_title": track_title,
            "track_mbid": track_mbid,
        }


    @classmethod
    def from_library_track(
            cls, raw_scrobble: Dict[str, Any], track: LibraryFile,
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
        date_raw = raw_scrobble.get("date")
        if date_raw is not None:
            scrobble_time = int(date_raw.get("uts"))
        else:
            scrobble_time = None

        return cls(
            track_source=track_source,
            epoch_time=scrobble_time,

            artist_name=track.artist_name,
            artist_mbid=track.artist_mbid,

            album_name=track.album_name,
            album_mbid=track.album_mbid,

            track_title=track.track_title,
            track_mbid=track.track_mbid,
            track_length=round(track.track_length, 1),
        )

    @classmethod
    def from_musicbrainz_track(cls, raw_scrobble: Dict[str, Any], track: ReleaseTrack):
        """
        Use MusicBrainz track duration and construct a Scrobble with the help of normal scrobble data.
        Args:
            raw_scrobble:
            track:

        Returns:

        """
        scrobble_info = cls.parse_raw_scrobble(raw_scrobble)
        # Use length from ReleaseTrack
        track_length = track.track_length

        return cls(
            track_source=TrackSourceType.MUSICBRAINZ,
            epoch_time=scrobble_info["time"],

            artist_name=scrobble_info["artist_name"],
            artist_mbid=scrobble_info["artist_mbid"],

            album_name=scrobble_info["album_name"],
            album_mbid=scrobble_info["album_mbid"],

            track_title=scrobble_info["track_title"],
            track_mbid=scrobble_info["track_mbid"],
            track_length=track_length,
        )

    @classmethod
    def from_youtube(cls, raw_scrobble: Dict[str, Any], video_duration: int):
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
        scrobble_info = cls.parse_raw_scrobble(raw_scrobble)
        # Use length from the video
        track_length = video_duration

        return cls(
            track_source=TrackSourceType.YOUTUBE,
            epoch_time=scrobble_info["time"],

            artist_name=scrobble_info["artist_name"],
            artist_mbid=scrobble_info["artist_mbid"],

            album_name=scrobble_info["album_name"],
            album_mbid=scrobble_info["album_mbid"],

            track_title=scrobble_info["track_title"],
            track_mbid=scrobble_info["track_mbid"],
            track_length=track_length,
        )

    @classmethod
    def from_basic_data(cls, raw_scrobble: Dict[str, Any]):
        """
        Use just basic scrobble data and instance a Scrobble. Length, for example, will be empty though.

        Args:
            raw_scrobble:
                Raw scrobble dict (one entry) as exported from last.fm.

        Returns:
            Scrobble instance constructed only scrobble data.
        """
        scrobble_info = cls.parse_raw_scrobble(raw_scrobble)

        return cls(
            track_source=TrackSourceType.JUST_SCROBBLE,
            epoch_time=scrobble_info["time"],

            artist_name=scrobble_info["artist_name"],
            artist_mbid=scrobble_info["artist_mbid"],

            album_name=scrobble_info["album_name"],
            album_mbid=scrobble_info["album_mbid"],

            track_title=scrobble_info["track_title"],
            track_mbid=scrobble_info["track_mbid"],
            track_length=None,
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
            "Track Source",
            "Scrobble Time",
            "Artist",
            "Artist MBID",
            "Album",
            "Album MBID",
            "Track",
            "Track MBID",
            "Track Length"
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
        ]
from typing import Union, Optional

from mutagen import FileType

from .utilities import get_mutagen_attribute


class LibraryFile:
    __slots__ = (
        "file_path",
        "track_length",
        "artist_name",
        "artist_mbid",
        "album_name",
        "album_mbid",
        "track_title",
        "track_mbid",
    )

    def __init__(self, **kwargs):
        self.file_path: str = kwargs.pop("file_path")
        self.track_length: Union[int, float] = kwargs.pop("track_length")

        self.artist_name: Optional[str] = kwargs.get("artist_name")
        self.artist_mbid: Optional[str] = kwargs.get("artist_mbid")

        self.album_name: Optional[str] = kwargs.get("album_name")
        self.album_mbid: Optional[str] = kwargs.get("album_mbid")

        self.track_title: Optional[str] = kwargs.get("track_title")
        self.track_mbid: Optional[str] = kwargs.get("track_mbid")

    @classmethod
    def from_mutagen(cls, file: FileType):
        artist_name = get_mutagen_attribute(file, "artist")
        artist_mbid = get_mutagen_attribute(file, "musicbrainz_artistid")

        album_name = get_mutagen_attribute(file, "album")
        album_mbid = get_mutagen_attribute(file, "musicbrainz_albumid")

        track_title = get_mutagen_attribute(file, "title")
        track_mbid = get_mutagen_attribute(file, "musicbrainz_trackid")

        return cls(
            file_path=file.filename,
            track_length=float(file.info.length),
            artist_name=artist_name,
            artist_mbid=artist_mbid,
            album_name=album_name,
            album_mbid=album_mbid,
            track_title=track_title,
            track_mbid=track_mbid,
        )

    def dump(self) -> dict:
        return {
            "file_path": self.file_path,
            "track_length": self.track_length,
            "artist_name": self.artist_name,
            "artist_mbid": self.artist_mbid,
            "album_name": self.album_name,
            "album_mbid": self.album_mbid,
            "track_title": self.track_title,
            "track_mbid": self.track_mbid,
        }

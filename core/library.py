from typing import Union, Optional

from mutagen import FileType

from .utilities import get_mutagen_attribute
from .genres import genre_state


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
        "genre_list",
    )

    def __init__(self, **kwargs):
        self.file_path: str = kwargs.pop("file_path")
        self.track_length: Union[int, float] = kwargs.pop("track_length")

        # This way we avoid empty strings
        self.artist_name: Optional[str] = kwargs.get("artist_name") or None
        self.artist_mbid: Optional[str] = kwargs.get("artist_mbid") or None

        self.album_name: Optional[str] = kwargs.get("album_name") or None
        self.album_mbid: Optional[str] = kwargs.get("album_mbid") or None

        self.track_title: Optional[str] = kwargs.get("track_title") or None
        self.track_mbid: Optional[str] = kwargs.get("track_mbid") or None

        self.genre_list: Optional[str] = kwargs.get("genre_list") or None

    def __str__(self):
        return f"<LibraryFile: {self.artist_name} - {self.album_name} - {self.track_title} ({self.track_length})>"

    @classmethod
    def from_mutagen(cls, file: FileType):
        artist_name = get_mutagen_attribute(file, "artist")
        artist_mbid = get_mutagen_attribute(file, "musicbrainz_artistid")

        album_name = get_mutagen_attribute(file, "album")
        album_mbid = get_mutagen_attribute(file, "musicbrainz_albumid")

        track_title = get_mutagen_attribute(file, "title")
        track_mbid = get_mutagen_attribute(file, "musicbrainz_trackid")

        genres_raw = get_mutagen_attribute(file, "genre")
        genres = [
            a.strip(" ").title() for a in genres_raw.split(",") if a.strip(" ").title() in genre_state.full_genre_list
        ] if genres_raw is not None else None

        return cls(
            file_path=file.filename,
            track_length=float(file.info.length),
            artist_name=artist_name,
            artist_mbid=artist_mbid,
            album_name=album_name,
            album_mbid=album_mbid,
            track_title=track_title,
            track_mbid=track_mbid,
            genre_list=genres,
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
            "genre_list": self.genre_list,
        }

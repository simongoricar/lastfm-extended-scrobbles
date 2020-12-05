import requests as req
from urllib.parse import urlencode

BASE_MB_RELEASE_URL = "https://musicbrainz.org/ws/2/release"


class ReleaseTrack:
    __slots__ = (
        "track_title", "track_mbid", "track_length", "album_name", "album_mbid"
    )

    def __init__(self, **kwargs):
        # TODO rename album_name arguments to album_title for accuracy (see Scobble and LibraryFile as well)
        self.track_title = kwargs.pop("track_title")
        self.track_mbid = kwargs.pop("track_mbid")
        # .pop for required kwargs, .get for optional
        self.track_length = kwargs.get("track_length")

        self.album_name = kwargs.pop("album_name")
        self.album_mbid = kwargs.pop("album_mbid")

    @classmethod
    def from_track_mbid(cls, track_mbid: str):
        # TODO cache this?
        params = {
            "fmt": "json",
            "track": track_mbid
        }

        full_url = f"{BASE_MB_RELEASE_URL}?{urlencode(params)}"
        # Send query to musicbrainz and get the release with this track back
        resp = req.get(full_url)
        data_raw = resp.json()

        d_release_count = data_raw.get("release_count")
        if d_release_count is None or d_release_count < 1:
            return None

        d_release_first = data_raw.get("releases")[0]
        d_media = d_release_first.get("media")[0]
        d_tracks = d_media.get("tracks")

        for track in d_tracks:
            # On first match, return the track
            if track.get("id") == track_mbid:
                track_title = track.get("title")
                track_mbid = track.get("id")

                try:
                    track_length = round(int(track.get("length")) / 100, 1)
                except TypeError:
                    track_length = None

                album_name = d_release_first.get("title")
                album_mbid = d_release_first.get("id")

                return cls(
                    track_title=track_title,
                    track_mbid=track_mbid,
                    track_length=track_length,
                    album_name=album_name,
                    album_mbid=album_mbid,
                )

        return None

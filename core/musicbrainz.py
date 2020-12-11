import logging
import requests as req
from urllib.parse import urlencode

from typing import Dict, Optional

from .configuration import PROJECT_NAME, VERSION, REPOSITORY

log = logging.getLogger(__name__)

BASE_MB_RELEASE_URL = "https://musicbrainz.org/ws/2/release"

track_mbid_to_releasetrack_cache: Dict[str, Optional["ReleaseTrack"]] = {}


class ReleaseTrack:
    __slots__ = (
        "track_title",
        "track_mbid",
        "track_length",
        "album_title",
        "album_mbid"
    )

    GLOBAL_HEADERS = {
        "fmt": "json",
        # https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting
        "User-Agent": f"{PROJECT_NAME}/{VERSION} ( {REPOSITORY} )",
    }

    def __init__(self, **kwargs):
        # .pop for required kwargs, .get for optional
        self.track_title = kwargs.pop("track_title")
        self.track_mbid = kwargs.pop("track_mbid")
        self.track_length = kwargs.get("track_length")

        self.album_title = kwargs.pop("album_title")
        self.album_mbid = kwargs.pop("album_mbid")

    @classmethod
    def from_track_mbid(cls, track_mbid: str, ignore_cache: bool = False):
        if not ignore_cache and track_mbid in track_mbid_to_releasetrack_cache:
            # Cache hit, return this one
            log.debug("ReleaseTrack.from_track_mbid: cache hit")
            return track_mbid_to_releasetrack_cache[track_mbid]

        log.debug("ReleaseTrack.from_track_mbid: cache miss, requesting")

        params = {
            **cls.GLOBAL_HEADERS,
            "track": track_mbid
        }

        full_url = f"{BASE_MB_RELEASE_URL}?{urlencode(params)}"
        # Send query to musicbrainz and get the release with this track back
        resp = req.get(full_url)
        data_raw = resp.json()

        d_release_count = data_raw.get("release-count")
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
                    track_length = round(int(track.get("length")) / 1000, 1)
                except TypeError:
                    track_length = None

                album_name = d_release_first.get("title")
                album_mbid = d_release_first.get("id")

                # Cache and return
                instance = cls(
                    track_title=track_title,
                    track_mbid=track_mbid,
                    track_length=track_length,
                    album_title=album_name,
                    album_mbid=album_mbid,
                )
                track_mbid_to_releasetrack_cache[track_mbid] = instance
                return instance

        # Cache and return
        track_mbid_to_releasetrack_cache[track_mbid] = None
        return None

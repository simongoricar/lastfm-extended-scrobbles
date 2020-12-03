import logging
import glob
import time
from os import path
from json import load

from mutagen import File

from core.configuration import config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

##
# 1. Build music library cache
##

# 1.1) Collect audio files
log.info("Collecting audio files.")

# Recursively build a list of audio files
globs = [path.join(config.MUSIC_LIBRARY_ROOT, f"**/*.{ext_glob}") for ext_glob in [
    # Most types that tinytag supports
    "mp3", "ogg", "wav", "flac", "m4a"
]]

audio_files = []
for g in globs:
    audio_files.extend(glob.glob(g, recursive=True))

audio_files.sort()

# DEBUGONLY
audio_files = audio_files[0:150]

audio_files_amount = len(audio_files)

log.info(f"Collected {audio_files_amount} audio files.")

# 1.2) Build audio metadata cache
log.info(f"Building metadata cache...")
t_start = time.time()

cache_by_album = {}
cache_by_albumartist = {}
cache_by_title = {}
cache_by_track_mbid = {}

c = 0
for audio_file in audio_files:
    # Load file metadata
    tags = File(audio_file, easy=True)

    album = tags.get("album")
    albumartist = tags.get("albumartist")
    title = tags.get("title")
    track_mbid = tags.get("musicbrainz_trackid")

    if album is not None:
        cache_by_album[album[0]] = tags
    if albumartist is not None:
        cache_by_albumartist[albumartist[0]] = tags
    if title is not None:
        cache_by_title[title[0]] = tags
    if track_mbid is not None:
        cache_by_track_mbid[track_mbid[0]] = tags

    # Log progress
    if c % 50 == 0:
        log.info(f"Progress: {c} files.")
    c += 1

t_total = round(time.time() - t_start, 1)
log.info(f"Metadata cache built in {t_total}s")


##
# 2. Load scrobbles
##
log.info("Loading scrobbles file...")
t_start = time.time()

with open(config.SCROBBLES_JSON_PATH, "r", encoding="utf8") as scrobbles_file:
    scrobbles_raw = load(scrobbles_file)

# 2.1) Flatten json pages
scrobbles = [item for sublist in scrobbles_raw for item in sublist]
scrobbles_len = len(scrobbles)

t_total = round(time.time() - t_start, 1)
log.info(f"Scrobbles file read and parsed in {t_total}s")
log.info(f"{scrobbles_len} scrobbles loaded.")

##
# 3. Generate statistics
##

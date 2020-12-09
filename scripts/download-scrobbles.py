#################
# This script will manually download the scrobbles from last.fm's api
#
# Usage:
# When calling this script, pass your username with the parameters "--username [username]".
# If no parameter is passed, you will be asked for the username interactively.
#################
import logging
import time
import os
import requests
import sys
import getopt
import json
from typing import Optional, List
from urllib.parse import urlencode

# Add the base directory as a path for the import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# Otherwise this won't work
from core.configuration import config

logging.basicConfig(level=config.VERBOSITY)
log = logging.getLogger(__name__)

# To avoid leaking your api key
logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"

# Parse command line arguments
username: Optional[str] = None
try:
    if len(sys.argv[1:]) < 1:
        raise getopt.GetoptError("no args")

    opts, args = getopt.getopt(sys.argv[1:], "u:", "username=")

    for opt, arg in opts:
        if opt in ("-u", "--username"):
            username = arg

except getopt.GetoptError:
    # Fall back to interactive
    log.warning("No -u [username]/--username [username] passed, falling back to interactive.")
    username = input("Enter your username:")

log.info(f"Chosen username: {username}")


def request_page(lastfm_username: str, page_num: int) -> dict:
    parameters = {
        "api_key": config.LASTFM_API_KEY,
        "format": "json",
        "method": "user.getRecentTracks",
        "limit": "200",
        "user": lastfm_username,
        "page": page_num,
        "extended": 1
    }

    full_url = LASTFM_API_URL + "?" + urlencode(parameters)
    resp = requests.get(full_url)

    return resp.json()


scrobbles_pages: List[List[dict]] = []
page_counter: int = 1

# Request first page and find the total number of pages
log.info("Requesting first page.")

first_request = request_page(username, page_counter)
recenttracks_raw = first_request.get("recenttracks") or {}
scrobbles_pages.append(recenttracks_raw.get("track") or [])

total_pages = int(recenttracks_raw.get("@attr").get("totalPages"))
log.info(f"Total pages: {total_pages}, downloading...")

# Request the rest of the pages
while page_counter <= total_pages:
    log.info(f"Requesting page {page_counter}/{total_pages}")

    new_page: dict = request_page(username, page_counter)
    recenttracks_raw: dict = new_page.get("recenttracks") or {}

    tracks: List[dict] = recenttracks_raw.get("track") or []
    scrobbles_pages.append(tracks)

    page_counter += 1
    time.sleep(0.2)

# Write the results to json file
filename: str = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        f"scrobbles-{username}-{int(time.time())}.json"
    )
)
log.info(f"Saving scrobbles to file: {filename}")

with open(filename, "w", encoding="utf8") as sc_out:
    json.dump(scrobbles_pages, sc_out, ensure_ascii=False)

log.info("DONE")

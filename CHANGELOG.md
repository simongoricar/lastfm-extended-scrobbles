1.2
- Added: exact metadata match (if this one fails, we try partial match as previously)
- Changed: improved output file naming (timestamped name, adds a random suffix if about to overwrite)
- Changed: now using unicode quick ratio for partial matches
- Changed: a bunch of internal optimisations, added stability and code cleanup
- Fixed: fix crash on missing audio file tags

1.1
- Added: new column - genre! (data from Last.fm tags using Beets' genre list)
- Added: new column - track love (data from Last.fm)
- Added: scrobble data downloader (see `scripts/download-scrobbles.py`)
- Changed: renamed spreadsheed columns to snake_case
- Fixed: crash on corrupt audio file
- Fixed: ending stats not counting MusicBrainz matches

1.0
- Added: initial version (four modes of search)

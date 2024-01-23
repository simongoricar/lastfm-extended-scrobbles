use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_with::{serde_as, TimestampSeconds};

use crate::lastfm::ScrobbledTrack;

/// A last.fm scrobble snapshot.
///
/// Invariants:
/// - `scrobbled_tracks` must include *all* last.fm-scrobbled tracks between `from` and `to`.
#[derive(Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct ScrobbleArchive {
    #[serde(flatten)]
    pub metadata: ScrobbleArchiveMetadata,

    /// List of all archived scrobbles.
    pub scrobbled_tracks: Vec<ScrobbledTrack>,
}

impl ScrobbleArchive {
    pub fn generate_file_name(&self) -> String {
        let from_timestamp = self.metadata.from.timestamp();
        let to_timestamp = self.metadata.to.timestamp();

        let username_ascii = deunicode::deunicode_with_tofu(&self.metadata.username, "_");

        format!(
            "scrobble-archive_user-{}_from-{}_to-{}.json",
            username_ascii, from_timestamp, to_timestamp,
        )
    }
}

#[serde_as]
#[derive(Serialize, Deserialize, Clone, PartialEq, Eq)]
pub struct ScrobbleArchiveMetadata {
    /// Date and time of archival.
    #[serde_as(as = "TimestampSeconds<i64>")]
    pub archived_at: DateTime<Utc>,

    /// last.fm username of the person whose scrobbles were archived.
    pub username: String,

    /// Date and time of the oldest included scrobble.
    #[serde_as(as = "TimestampSeconds<i64>")]
    pub from: DateTime<Utc>,

    /// Date and time of the most recent included scrobble.
    #[serde_as(as = "TimestampSeconds<i64>")]
    pub to: DateTime<Utc>,
}

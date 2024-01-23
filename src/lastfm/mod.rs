use std::{cmp::Ordering, fmt::Display, str::FromStr};

use chrono::{DateTime, Utc};
use miette::{miette, Context, IntoDiagnostic};
use reqwest::Response;
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_with::{serde_as, DeserializeFromStr, SerializeDisplay, TimestampSeconds};
use thiserror::Error;
use url::Url;

use self::errors::LastFmError;

pub mod errors;

const DEFAULT_LAST_FM_API_ROOT_URL: &str = "http://ws.audioscrobbler.com/2.0/";


#[derive(Debug, Deserialize, Serialize)]
pub struct LastFmApiErrorResponse {
    pub message: Option<String>,
    pub error: i32,
}


/// Descriptions of fields in this struct and the structs that make it up are based on analyzing
/// data returned from the API for about 60k scrobbles. Still, it's possible that some fields will
/// not be completely described.
#[derive(Deserialize, Serialize, Debug)]
struct RawUserRecentTracksResponse {
    recenttracks: RawRecentTracksField,
}

#[derive(Deserialize, Serialize, Debug)]
struct RawRecentTracksField {
    track: Vec<RawRecentTrack>,

    #[serde(rename = "@attr")]
    at_attr: RawRootAttr,
}

/// Invariants:
/// - The `artist` field is always present
///   (but has two variants depending on the `extended` parameter of the API request).
/// - The `date` field is always present.
/// - `streamable` is always present and can contain the string "1" or "0".
/// - `image` always has four image elements.
/// - `name` can *not* be an empty string.
/// - `url` can not be an empty string.
/// - `loved` can contain the string "1" or "0".
/// - `mbid` can be an empty string.
#[derive(Deserialize, Serialize, Debug)]
struct RawRecentTrack {
    artist: RawArtistInfo,
    streamable: String,
    image: Vec<RawImageInfo>,
    /// NOTE: Can be an empty string.
    mbid: String,
    album: RawAlbumInfo,
    name: String,
    url: String,
    date: RawDateInfo,
    loved: String,

    #[serde(rename = "@attr")]
    attr: Option<RawRecentTrackAttr>,
}

#[derive(Deserialize, Serialize, Debug)]
struct RawDateInfo {
    /// Unix epoch in seconds.
    uts: String,

    /// Human-readable time (format: "DAY MONTH YEAR, HOUR:MINUTE").
    #[serde(rename = "#text")]
    text: String,
}

/// Invariants:
/// - `text` is always a non-empty string.
/// - `mbid` can be an empty string.
#[derive(Deserialize, Serialize, Debug)]
struct RawNormalArtistInfo {
    /// NOTE: Can be an empty string.
    mbid: String,

    #[serde(rename = "#text")]
    text: String,
}

/// Invariants:
/// - `name` is always a non-empty string.
/// - `url` is always a non-empty string.
/// - `mbid` can be an empty string.
/// - Not all artists have images (i.e. `image` can be an empty vector).
#[derive(Deserialize, Serialize, Debug)]
struct RawExtendedArtistInfo {
    /// NOTE: Can be an empty string.
    mbid: String,

    name: String,

    url: String,

    #[serde(default)]
    image: Vec<RawImageInfo>,
}

/// Contains two variants of the raw artist information structure.
///
/// If the API request was performed with `extended=1`,
/// you'll get [`RawExtendedArtistInfo`], otherwise only [`RawNormalArtistInfo`].
#[derive(Deserialize, Serialize, Debug)]
enum RawArtistInfo {
    Extended(RawExtendedArtistInfo),
    Normal(RawNormalArtistInfo),
}

/// Possible states:
/// - Both fields are non-empty strings.
/// - Both fields are empty strings (most common when scrobbling YouTube and such).
/// - `text` is a non-empty string and `mbid` is an empty string.
///
/// Namely, if `text` is an empty string, so is `mbid`.
#[derive(Deserialize, Serialize, Debug)]
struct RawAlbumInfo {
    mbid: String,

    #[serde(rename = "#text")]
    text: String,
}

/// Invariants:
/// - Size` is one of: "small", "medium", "large", or "extralarge".
/// - `text` can be an empty string.
/// - If `text` is not an empty string, it contains a URL starting with `https://lastfm.freetls.fastly.net`.
#[derive(Deserialize, Serialize, Debug)]
struct RawImageInfo {
    size: String,

    #[serde(rename = "#text")]
    text: String,
}

#[derive(Deserialize, Serialize, Debug)]
struct RawRecentTrackAttr {
    nowplaying: String,
}

#[derive(Deserialize, Serialize, Debug)]
#[allow(non_snake_case)]
struct RawRootAttr {
    user: String,
    totalPages: String,
    page: String,
    perPage: String,
    total: String,
}



#[derive(Deserialize, Serialize, Debug)]
pub struct UserRecentTracks {
    pub username: String,

    pub current_page: usize,
    pub total_pages: usize,
    pub scrobbles_per_page: usize,
    pub total_scrobbles: usize,

    /// Scrobbles on this page.
    pub scrobbled_tracks: Vec<ScrobbledTrack>,
}

macro_rules! parse_with_json_structure_error_report {
    ($field:expr, $target_type:tt, $wrapper:expr) => {
        $field
            .parse::<$target_type>()
            .into_diagnostic()
            .wrap_err_with(|| $wrapper)
            .map_err(|error| LastFmError::JsonStructureError { reason: error })
    };
}

impl TryFrom<RawUserRecentTracksResponse> for UserRecentTracks {
    type Error = LastFmError;

    fn try_from(value: RawUserRecentTracksResponse) -> Result<Self, Self::Error> {
        let username = value.recenttracks.at_attr.user;

        let current_page = parse_with_json_structure_error_report!(
            value.recenttracks.at_attr.page,
            usize,
            miette!("Failed to parse field page in @attr.")
        )?;

        let total_pages = parse_with_json_structure_error_report!(
            value.recenttracks.at_attr.totalPages,
            usize,
            miette!("Failed to parse field totalPages in @attr.")
        )?;

        let scrobbles_per_page = parse_with_json_structure_error_report!(
            value.recenttracks.at_attr.perPage,
            usize,
            miette!("Failed to parse field perPage in @attr.")
        )?;

        let total_scrobbles = parse_with_json_structure_error_report!(
            value.recenttracks.at_attr.total,
            usize,
            miette!("Failed to parse field total in @attr.")
        )?;

        let scrobbled_tracks = value
            .recenttracks
            .track
            .into_iter()
            .map(ScrobbledTrack::try_from)
            .collect::<Result<Vec<_>, _>>()?;


        Ok(UserRecentTracks {
            username,
            current_page,
            total_pages,
            scrobbles_per_page,
            total_scrobbles,
            scrobbled_tracks,
        })
    }
}

#[serde_as]
#[derive(Serialize, Deserialize, Debug, PartialEq, Eq, Clone)]
pub struct ScrobbledTrack {
    /// Track name.
    pub track_name: String,

    /// MusicBrainz ID associated with this track, if any.
    pub track_mbid: Option<MusicBrainzId>,

    /// Last.fm URL for this track.
    pub track_last_fm_url: Url,

    /// Images related to this track.
    pub track_images: Vec<Image>,

    /// Is the track streamable on last.fm or not.
    pub is_track_streamable: bool,

    /// Artist information.
    pub artist: Artist,

    /// Album information, if any.
    pub album: Option<Album>,

    /// When the track was scrobbled.
    #[serde_as(as = "TimestampSeconds<i64>")]
    pub scrobbled_at: DateTime<Utc>,
}

impl TryFrom<RawRecentTrack> for ScrobbledTrack {
    type Error = LastFmError;

    fn try_from(value: RawRecentTrack) -> Result<Self, Self::Error> {
        /*
         * Parse artist information
         */

        let artist = match value.artist {
            RawArtistInfo::Extended(extended_artist) => {
                // Ensure `text` is a non-empty string.
                if extended_artist.name.is_empty() {
                    return Err(LastFmError::JsonStructureError {
                        reason: miette!(
                            "Unexpected structure: artist.name field is an empty string."
                        ),
                    });
                }

                let artist_mbid: Option<MusicBrainzId> = match extended_artist.mbid.is_empty() {
                    true => None,
                    false => Some(
                        MusicBrainzId::new_artist_id(extended_artist.mbid)
                            .into_diagnostic()
                            .wrap_err_with(|| miette!("Could not parse artist.mbid field."))
                            .map_err(LastFmError::json_structure_error)?,
                    ),
                };

                let artist_images = extended_artist
                    .image
                    .into_iter()
                    .map(Image::try_from)
                    .collect::<Result<Vec<_>, _>>()?;

                Artist {
                    name: extended_artist.name,
                    mbid: artist_mbid,
                    images: artist_images,
                }
            }
            RawArtistInfo::Normal(normal_artist) => {
                // Ensure `text` is a non-empty string.
                if normal_artist.text.is_empty() {
                    return Err(LastFmError::JsonStructureError {
                        reason: miette!(
                            "Unexpected structure: artist.text field is an empty string."
                        ),
                    });
                }

                let artist_mbid: Option<MusicBrainzId> = match normal_artist.mbid.is_empty() {
                    true => None,
                    false => Some(
                        MusicBrainzId::new_artist_id(normal_artist.mbid)
                            .into_diagnostic()
                            .wrap_err_with(|| miette!("Could not parse artist.mbid field."))
                            .map_err(LastFmError::json_structure_error)?,
                    ),
                };

                Artist {
                    name: normal_artist.text,
                    mbid: artist_mbid,
                    images: Vec::with_capacity(0),
                }
            }
        };



        /*
         * Parse album information
         */

        let album = if value.album.text.is_empty() && value.album.mbid.is_empty() {
            // Both the album title and its MusicBrainz ID are available.
            let album_mbid = MusicBrainzId::new_album_id(value.album.mbid)
                .into_diagnostic()
                .wrap_err_with(|| miette!("Failed to parse album.mbid field as a MusicBrainz ID!"))
                .map_err(LastFmError::json_structure_error)?;

            Some(Album {
                name: value.album.text,
                mbid: Some(album_mbid),
            })
        } else if !value.album.text.is_empty() && !value.album.mbid.is_empty() {
            // No information about the album is available.
            None
        } else if !value.album.text.is_empty() && value.album.mbid.is_empty() {
            // Only the album title is available (no MusicBrainz ID).
            Some(Album {
                name: value.album.text,
                mbid: None,
            })
        } else {
            // Unxpected combination: `text` is an empty string, but `mbid` is not?
            // This should raise an error as we need to fix it if such a thing can occur.
            panic!(
                "Invariant not upheld by the last.fm API data: \
                album.text is empty, but album.mbid contains some information?!"
            );
        };


        /*
         * Parse track information
         */

        let track_name = value.name;
        let track_mbid = match value.mbid.is_empty() {
            true => None,
            false => Some(
                MusicBrainzId::new_track_id(value.mbid)
                    .into_diagnostic()
                    .wrap_err_with(|| miette!("Failed to parse mbid field!"))
                    .map_err(LastFmError::json_structure_error)?,
            ),
        };


        if value.url.is_empty() {
            return Err(LastFmError::json_structure_error(miette!(
                "Invariant not upheld by the last.fm API data: \
                url field is an empty string"
            )));
        }

        let track_last_fm_url = Url::parse(&value.url)
            .into_diagnostic()
            .wrap_err_with(|| miette!("Failed to parse url field."))
            .map_err(LastFmError::json_structure_error)?;

        if track_last_fm_url.scheme() != "https" || track_last_fm_url.scheme() != "http" {
            return Err(LastFmError::json_structure_error(miette!(
                "Invalid track url (not a http(s) url): {}",
                track_last_fm_url
            )));
        }

        match track_last_fm_url.host_str() {
            Some(host) => {
                if !host.starts_with("www.last.fm") {
                    return Err(LastFmError::json_structure_error(miette!(
                        "Invalid track url (expected host www.last.fm): {}",
                        track_last_fm_url
                    )));
                }
            }
            None => {
                return Err(LastFmError::json_structure_error(miette!(
                    "Invalid track url (no host): {}",
                    track_last_fm_url
                )));
            }
        }


        /*
         * Parse scrobble datetime
         */

        let time_since_epoch = value
            .date
            .uts
            .parse::<i64>()
            .into_diagnostic()
            .wrap_err_with(|| miette!("Failed to parse date.uts as i64!"))
            .map_err(LastFmError::json_structure_error)?;

        let scrobbled_at = DateTime::<Utc>::from_timestamp(time_since_epoch, 0)
            .ok_or_else(|| miette!("Failed to parse date.uts: out of range."))
            .map_err(LastFmError::json_structure_error)?;


        /*
         * Parse track images and streamable status.
         */

        let track_images = value
            .image
            .into_iter()
            .map(Image::try_from)
            .collect::<Result<Vec<_>, _>>()?;

        let is_track_streamable = match value.streamable.as_str() {
            "1" => true,
            "0" => false,
            _ => {
                return Err(LastFmError::json_structure_error(miette!(
                    "Invalid streamable field value: {}",
                    value.streamable
                )))
            }
        };


        Ok(Self {
            artist,
            album,
            track_name,
            track_mbid,
            track_last_fm_url,
            track_images,
            scrobbled_at,
            is_track_streamable,
        })
    }
}


#[derive(Deserialize, Serialize, Debug, PartialEq, Eq, Clone)]
pub struct Artist {
    pub name: String,
    pub mbid: Option<MusicBrainzId>,
    pub images: Vec<Image>,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Eq, Clone)]
pub struct Album {
    pub name: String,
    pub mbid: Option<MusicBrainzId>,
}

#[derive(
    DeserializeFromStr,
    SerializeDisplay,
    Debug,
    PartialEq,
    Eq,
    Clone,
    Copy
)]
pub enum ImageSize {
    Small,
    Medium,
    Large,
    ExtraLarge,
}

impl Display for ImageSize {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ImageSize::Small => write!(f, "small"),
            ImageSize::Medium => write!(f, "medium"),
            ImageSize::Large => write!(f, "large"),
            ImageSize::ExtraLarge => write!(f, "extralarge"),
        }
    }
}

impl Ord for ImageSize {
    fn cmp(&self, other: &Self) -> Ordering {
        match (self, other) {
            (ImageSize::Small, ImageSize::Small) => Ordering::Equal,
            (ImageSize::Small, ImageSize::Medium) => Ordering::Less,
            (ImageSize::Small, ImageSize::Large) => Ordering::Less,
            (ImageSize::Small, ImageSize::ExtraLarge) => Ordering::Less,
            (ImageSize::Medium, ImageSize::Small) => Ordering::Greater,
            (ImageSize::Medium, ImageSize::Medium) => Ordering::Equal,
            (ImageSize::Medium, ImageSize::Large) => Ordering::Less,
            (ImageSize::Medium, ImageSize::ExtraLarge) => Ordering::Less,
            (ImageSize::Large, ImageSize::Small) => Ordering::Greater,
            (ImageSize::Large, ImageSize::Medium) => Ordering::Greater,
            (ImageSize::Large, ImageSize::Large) => Ordering::Equal,
            (ImageSize::Large, ImageSize::ExtraLarge) => Ordering::Less,
            (ImageSize::ExtraLarge, ImageSize::Small) => Ordering::Greater,
            (ImageSize::ExtraLarge, ImageSize::Medium) => Ordering::Greater,
            (ImageSize::ExtraLarge, ImageSize::Large) => Ordering::Greater,
            (ImageSize::ExtraLarge, ImageSize::ExtraLarge) => Ordering::Equal,
        }
    }
}

impl PartialOrd for ImageSize {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}


#[derive(Error, Debug)]
#[error("Unrecognized image size: {0}")]
pub struct ImageSizeParseError(String);

impl FromStr for ImageSize {
    type Err = ImageSizeParseError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "small" => Ok(Self::Small),
            "medium" => Ok(Self::Medium),
            "large" => Ok(Self::Large),
            "extralarge" => Ok(Self::ExtraLarge),
            unrecognized => Err(ImageSizeParseError(unrecognized.to_string())),
        }
    }
}

/// **This enum does not list all available MusicBrainz entity types!**
/// It lists only the ones that appear in the last.fm scrobbling history API.
#[derive(SerializeDisplay, DeserializeFromStr, Debug, PartialEq, Eq, Clone)]
pub enum MusicBrainzEntityType {
    Artist,
    Album,
    Track,
}

impl Display for MusicBrainzEntityType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            MusicBrainzEntityType::Artist => write!(f, "artist"),
            MusicBrainzEntityType::Album => write!(f, "album"),
            MusicBrainzEntityType::Track => write!(f, "track"),
        }
    }
}

#[derive(Error, Debug)]
#[error("Unrecognized MusicBrainz entity type: {0}")]
pub struct MusicBrainzEntityTypeParseError(String);

impl FromStr for MusicBrainzEntityType {
    type Err = MusicBrainzEntityTypeParseError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "artist" => Ok(Self::Artist),
            "album" => Ok(Self::Album),
            "track" => Ok(Self::Track),
            _ => Err(MusicBrainzEntityTypeParseError(s.to_string())),
        }
    }
}

/// Returns `true` is the provided string is at a glance a valid MusicBrainz ID.
///
/// Note that this does not look up the ID in the database,
/// meaning the ID might still not exist.
/// This is essentially only a simple length check at the moment.
///
/// See <https://wiki.musicbrainz.org/MusicBrainz_Identifier> for more information.
fn is_ok_musicbrainz_id(id: &str) -> bool {
    id.len() == 36
}

#[derive(Error, Debug)]
#[error("Invalid MusicBrainz ID: {0}")]
pub struct InvalidMusicBrainzId(String);


#[derive(Serialize, Deserialize, Debug, PartialEq, Eq, Clone)]
pub struct MusicBrainzId {
    entity_type: MusicBrainzEntityType,
    mbid: String,
}

impl MusicBrainzId {
    #[inline]
    pub fn new_artist_id(artist_mbid: String) -> Result<Self, InvalidMusicBrainzId> {
        if !is_ok_musicbrainz_id(&artist_mbid) {
            return Err(InvalidMusicBrainzId(artist_mbid));
        }

        Ok(Self {
            entity_type: MusicBrainzEntityType::Artist,
            mbid: artist_mbid,
        })
    }

    #[inline]
    pub fn new_album_id(album_mbid: String) -> Result<Self, InvalidMusicBrainzId> {
        if !is_ok_musicbrainz_id(&album_mbid) {
            return Err(InvalidMusicBrainzId(album_mbid));
        }

        Ok(Self {
            entity_type: MusicBrainzEntityType::Album,
            mbid: album_mbid,
        })
    }

    #[inline]
    pub fn new_track_id(track_mbid: String) -> Result<Self, InvalidMusicBrainzId> {
        if !is_ok_musicbrainz_id(&track_mbid) {
            return Err(InvalidMusicBrainzId(track_mbid));
        }

        Ok(Self {
            entity_type: MusicBrainzEntityType::Track,
            mbid: track_mbid,
        })
    }
}



#[derive(Deserialize, Serialize, Debug, PartialEq, Eq, Clone)]
pub struct Image {
    pub size: ImageSize,
    pub url: Url,
}

impl TryFrom<RawImageInfo> for Image {
    type Error = LastFmError;

    fn try_from(value: RawImageInfo) -> Result<Self, Self::Error> {
        let size = value
            .size
            .parse::<ImageSize>()
            .into_diagnostic()
            .wrap_err_with(|| miette!("Failed to parse image size: {}", value.size))
            .map_err(LastFmError::json_structure_error)?;


        let url = Url::parse(&value.text)
            .into_diagnostic()
            .wrap_err_with(|| miette!("Failed to parse image url: {}", value.text))
            .map_err(LastFmError::json_structure_error)?;

        if url.scheme() != "https" || url.scheme() != "http" {
            return Err(LastFmError::json_structure_error(miette!(
                "Invalid image url (not a http(s) url): {}",
                url
            )));
        }

        match url.host_str() {
            Some(host) => {
                if !host.starts_with("lastfm.freetls.fastly.net") {
                    return Err(LastFmError::json_structure_error(miette!(
                        "Invalid image url (expected host lastfm.freetls.fastly.net): {}",
                        url
                    )));
                }
            }
            None => {
                return Err(LastFmError::json_structure_error(miette!(
                    "Invalid image url (no host): {}",
                    url
                )));
            }
        }


        Ok(Self { size, url })
    }
}



#[derive(Clone, PartialEq, Eq)]
pub struct UserRecentTracksOptions {
    /// How many scrobbles will be returned at once.
    /// At most 200, defaults to 50.
    pub results_per_page: usize,

    /// What page to fetch (one-indexed).
    /// Defaults to 1.
    pub page_to_fetch: usize,

    /// Whether to include extended scrobble data, which is
    /// at the moment:
    /// - An additional field indicating whether the user marked the track as loved.
    /// - A modified version of the artist field that includes the artist images in several sizes.
    ///
    /// *last.fm documentation*: "Includes extended data in each artist,
    /// and whether or not the user has loved each track"
    pub extended_data: bool,

    /// Scrobble datetime filter. Includes scrobbles at the specified time
    /// (i.e. it is an *inclusive* end of the range).
    ///
    /// *last.fm documentation*: "Beginning timestamp of a range - only display scrobbles after this time,
    /// in UNIX timestamp format (integer number of seconds since 00:00:00, January 1st 1970 UTC).
    /// This must be in the UTC time zone."
    pub from: Option<DateTime<Utc>>,

    /// Scrobble datetime filter. Does not include scrobbles at the specified time
    /// (i.e. it is an *exclusive* end of the range).
    ///
    /// *last.fm documentation*: "End timestamp of a range - only display scrobbles before this time,
    /// in UNIX timestamp format (integer number of seconds since 00:00:00, January 1st 1970 UTC).
    /// This must be in the UTC time zone."
    pub to: Option<DateTime<Utc>>,
}

impl Default for UserRecentTracksOptions {
    fn default() -> Self {
        Self {
            results_per_page: 200,
            page_to_fetch: 1,
            extended_data: true,
            from: None,
            to: None,
        }
    }
}


/// Documentation: https://www.last.fm/api/show/user.getRecentTracks
fn build_get_user_recent_tracks_url(
    base_url: &Url,
    username: &str,
    api_key: &str,
    options: UserRecentTracksOptions,
) -> Url {
    let mut url = base_url.clone();
    let mut query_mut = url.query_pairs_mut();

    query_mut.append_pair("method", "user.getrecenttracks");
    query_mut.append_pair("format", "json");


    query_mut.append_pair("limit", &options.results_per_page.to_string());
    query_mut.append_pair("user", username);
    query_mut.append_pair("page", &options.page_to_fetch.to_string());

    if let Some(from_date_time) = options.from {
        let epoch_timestamp = from_date_time.timestamp();
        query_mut.append_pair("from", &epoch_timestamp.to_string());
    }

    if let Some(to_date_time) = options.to {
        let epoch_timestamp = to_date_time.timestamp();
        query_mut.append_pair("to", &epoch_timestamp.to_string());
    }

    query_mut.append_pair(
        "extended",
        match options.extended_data {
            true => "1",
            false => "0",
        },
    );

    query_mut.append_pair("api_key", api_key);

    drop(query_mut);
    url
}


/// Decode the body of a [`reqwest::Response`][reqwest::Response] as JSON into
/// some `Deserializable` structure.
///
/// Returns [`LastFmError::JsonDecodingError`][LastFmError::JsonDecodingError]
/// if the body cannot be deserialized.
async fn decode_json<S>(response: Response) -> Result<S, LastFmError>
where
    S: DeserializeOwned,
{
    let full_body = response.bytes().await?;
    Ok(serde_json::from_slice(&full_body)?)
}

pub struct Client {
    client: reqwest::Client,
    base_url: Url,
    api_key: String,
}

impl Client {
    pub fn new<K>(api_key: K, base_url: Option<Url>) -> Result<Self, LastFmError>
    where
        K: Into<String>,
    {
        let client = reqwest::Client::builder().https_only(true).build()?;

        let base_url = match base_url {
            Some(url) => url,
            None => Url::parse(DEFAULT_LAST_FM_API_ROOT_URL)?,
        };

        Ok(Self {
            client,
            base_url,
            api_key: api_key.into(),
        })
    }

    pub async fn get_user_recent_tracks<S>(
        &self,
        username: S,
        options: UserRecentTracksOptions,
    ) -> Result<UserRecentTracks, LastFmError>
    where
        S: AsRef<str>,
    {
        let username = username.as_ref();

        let final_url =
            build_get_user_recent_tracks_url(&self.base_url, username, &self.api_key, options);

        let response = self
            .client
            .get(final_url)
            .send()
            .await
            .map_err(LastFmError::Reqwest)?;


        let status = response.status();
        if !status.is_success() {
            // Attempt to deserialize an error.
            let error_response: LastFmApiErrorResponse = decode_json(response).await?;
            Err(LastFmError::ApiError(error_response))
        } else {
            // Attempt to deserialize normal data.
            let raw_response_data: RawUserRecentTracksResponse = decode_json(response).await?;
            let scrobbles = UserRecentTracks::try_from(raw_response_data)?;

            Ok(scrobbles)
        }
    }
}

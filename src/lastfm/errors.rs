use miette::Diagnostic;
use thiserror::Error;

use super::LastFmApiErrorResponse;

#[derive(Error, Debug, Diagnostic)]
pub enum LastFmError {
    #[error("API error: {0:?}")]
    ApiError(LastFmApiErrorResponse),

    #[error("reqwest error: {0}")]
    Reqwest(#[from] reqwest::Error),

    #[error("url parse error: {0}")]
    UrlParseError(#[from] url::ParseError),

    #[error("failed to decode JSON response: {0}")]
    JsonDecodingError(#[from] serde_json::Error),

    #[error("JSON response had an unexpected structure: {reason:?}")]
    JsonStructureError { reason: miette::Report },
}

impl LastFmError {
    pub fn json_structure_error<R>(reason: R) -> Self
    where
        R: Into<miette::Report>,
    {
        Self::JsonStructureError {
            reason: reason.into(),
        }
    }
}

use std::{fs::File, path::PathBuf};

use chrono::{DateTime, LocalResult, TimeZone, Utc};
use euphony_configuration::DirectoryScan;
use inversion_list::InversionMap;
use memmap2::Mmap;
use miette::{miette, Context, IntoDiagnostic, Result};

use super::structure::ScrobbleArchiveMetadata;

pub struct ScrobbleArchiveFile {
    pub file_path: PathBuf,
    pub archive_metadata: ScrobbleArchiveMetadata,
}

impl ScrobbleArchiveFile {
    pub fn load_from_file(file_path: PathBuf) -> Result<Self> {
        let file = File::open(&file_path).into_diagnostic().wrap_err_with(|| {
            miette!(
                "Failed to open scrobble archive file {} for reading.",
                file_path.display()
            )
        })?;

        // Memory mapping + [`serde_json::from_slice`] is significantly faster
        // than [`serde_json::from_reader`].
        // See https://github.com/serde-rs/json/issues/160#issuecomment-841344394 for more information.

        // SAFETY: As far as I understand memory mapped files are fundamentally unsafe
        // as other processes could modify the underlying file in the middle of our read.
        // However, this is *extremely unlikely*.
        let memory_mapped_file = unsafe { Mmap::map(&file) }
            .into_diagnostic()
            .wrap_err_with(|| {
                miette!(
                    "Failed to memory map the scrobble archive file {}.",
                    file_path.display()
                )
            })?;

        let archive_metadata = serde_json::from_slice(&memory_mapped_file)
            .into_diagnostic()
            .wrap_err_with(|| {
                miette!(
                    "Failed to deserialize scrobble archive file {}.",
                    file_path.display()
                )
            })?;


        Ok(Self {
            file_path,
            archive_metadata,
        })
    }
}



pub struct ScrobbleArchiveScanner {
    user_archive_directory_path: PathBuf,
}

impl ScrobbleArchiveScanner {
    pub fn from_user_archive_path<P>(user_archive_directory_path: P) -> Self
    where
        P: Into<PathBuf>,
    {
        Self {
            user_archive_directory_path: user_archive_directory_path.into(),
        }
    }

    pub fn scan(&self) -> Result<Vec<ScrobbleArchiveFile>> {
        let scan = DirectoryScan::from_directory_path(&self.user_archive_directory_path, 0)
            .wrap_err_with(|| miette!("Could not perform directory scan."))?;

        let mut collected_scrobble_archives = Vec::with_capacity(scan.files.len());

        for file in scan.files {
            let file_path = file.path();

            let Some(file_extension) = file_path.extension() else {
                continue;
            };

            if file_extension.to_ascii_lowercase().ne("json") {
                continue;
            }


            let scrobble_archive_file = ScrobbleArchiveFile::load_from_file(file_path)
                .wrap_err_with(|| miette!("Failed to load scrobble archive file."))?;
            collected_scrobble_archives.push(scrobble_archive_file);
        }

        Ok(collected_scrobble_archives)
    }
}


/// Represents a span in time for which the scrobbles haven't been archived.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct MissingScrobblesTimeSpan {
    /// Represents the start of the range (inclusive).
    pub from: DateTime<Utc>,

    /// Represents the end of the range (exclusive).
    pub to: DateTime<Utc>,
}

// TODO Implement a way to deduct what scrobble time ranges are missing.
pub fn compute_missing_scrobble_archive_time_spans(
    existing_scrobble_archives: &[ScrobbleArchiveFile],
    until_time: DateTime<Utc>,
) -> Result<Vec<MissingScrobblesTimeSpan>> {
    let mut inversion_map =
        InversionMap::<i64, bool>::new_with_capacity(existing_scrobble_archives.len());

    // We mark the entire range from start of unix time until the specified `until_time`
    // as having missing data. We'll then overwrite the smaller ranges using `existing_scrobble_archives`
    // and finally filter out the ranges that are still missing.

    let until_timestamp_seconds = until_time.timestamp();
    inversion_map.insert_with_overwrite(0..=until_timestamp_seconds, false);

    for archive in existing_scrobble_archives {
        let from_timestamp_second = archive.archive_metadata.from.timestamp();
        let to_timestamp_second = archive.archive_metadata.to.timestamp();
        inversion_map.insert_with_overwrite(from_timestamp_second..=to_timestamp_second, true);
    }

    // Find the remaining ranges with the `false` value.
    let missing_archive_time_spans = inversion_map
        .into_iter()
        .filter_map(|entry| {
            // Filters out time ranges for which we already have scrobble archives.
            if entry.value {
                return None;
            }

            let from_timestamp_second = entry.start();
            let from_date_time = match Utc.timestamp_opt(*from_timestamp_second, 0) {
                LocalResult::Single(time) => time,
                LocalResult::None | LocalResult::Ambiguous(_, _) => {
                    return Some(Err(miette!(
                        "Could not parse UNIX timestamp as DateTime<Utc>."
                    )));
                }
            };

            let to_timestamp_second = entry.end();
            let to_date_time = match Utc.timestamp_opt(*to_timestamp_second, 0) {
                LocalResult::Single(time) => time,
                LocalResult::None | LocalResult::Ambiguous(_, _) => {
                    return Some(Err(miette!(
                        "Could not parse UNIX timestamp as DateTime<Utc>."
                    )));
                }
            };

            Some(Ok(MissingScrobblesTimeSpan {
                from: from_date_time,
                to: to_date_time,
            }))
        })
        .collect::<Result<Vec<_>, _>>()?;

    Ok(missing_archive_time_spans)
}

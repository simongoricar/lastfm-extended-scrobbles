use std::{
    collections::HashMap,
    env::current_dir,
    path::{Path, PathBuf},
};

use miette::{miette, Context, IntoDiagnostic, Result};

/// Returns the default configuration filepath, which is at
/// `{current directory}/data/configuration.toml`.
pub fn get_default_configuration_file_path() -> Result<PathBuf> {
    let mut configuration_filepath = current_dir()
        .into_diagnostic()
        .wrap_err_with(|| miette!("Could not get the current directory."))?;
    configuration_filepath.push("data/configuration.toml");

    if !configuration_filepath.exists() {
        panic!("Could not find configuration.toml in data directory.");
    }

    Ok(configuration_filepath)
}

#[must_use = "function returns the modified path"]
#[allow(dead_code)]
pub fn replace_placeholders_in_path(
    original_path: &Path,
    placeholders: HashMap<&'static str, String>,
) -> PathBuf {
    let mut path_string = original_path.to_string_lossy().to_string();

    for (key, value) in placeholders.into_iter() {
        path_string = path_string.replace(key, &value);
    }

    PathBuf::from(path_string)
}

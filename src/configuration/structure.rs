use std::{
    fs,
    path::{Path, PathBuf},
};

use miette::{miette, Context, IntoDiagnostic, Result};
use serde::Deserialize;
use tracing_subscriber::EnvFilter;

use super::{traits::ResolvableConfiguration, utilities::get_default_configuration_file_path};


#[derive(Clone)]
pub struct Configuration {
    pub logging: LoggingConfiguration,
    pub last_fm: LastFmConfiguration,
}

#[derive(Deserialize, Clone)]
pub struct UnresolvedConfiguration {
    logging: UnresolvedLoggingConfiguration,
    last_fm: UnresolvedLastFmConfiguration,
}

impl Configuration {
    pub fn load_from_path<P: AsRef<Path>>(configuration_file_path: P) -> Result<Self> {
        let configuration_file_path = configuration_file_path.as_ref();

        let configuration_file_contents = fs::read_to_string(configuration_file_path)
            .into_diagnostic()
            .wrap_err_with(|| miette!("Failed to read configuration file."))?;

        let unresolved_configuration: UnresolvedConfiguration =
            toml::from_str(&configuration_file_contents)
                .into_diagnostic()
                .wrap_err_with(|| miette!("Failed to parse configuration file as TOML."))?;

        let resolved_configuration = unresolved_configuration
            .resolve()
            .wrap_err_with(|| miette!("Failed to resolve configuration."))?;

        Ok(resolved_configuration)
    }

    pub fn load_from_default_path() -> Result<Self> {
        let default_configuration_file_path = get_default_configuration_file_path()
            .wrap_err_with(|| miette!("Failed to construct default configuration file path."))?;

        Self::load_from_path(default_configuration_file_path)
    }
}

impl ResolvableConfiguration for UnresolvedConfiguration {
    type Resolved = Configuration;

    fn resolve(self) -> Result<Self::Resolved> {
        let logging = self.logging.resolve()?;
        let last_fm = self.last_fm.resolve()?;

        Ok(Self::Resolved { logging, last_fm })
    }
}


/*
 * Logging configuration
 */

#[derive(Deserialize, Clone)]
struct UnresolvedLoggingConfiguration {
    console_output_level_filter: String,
    log_file_output_level_filter: String,
    log_file_output_directory: String,
}

#[derive(Clone)]
pub struct LoggingConfiguration {
    pub console_output_level_filter: String,
    pub log_file_output_level_filter: String,
    pub log_file_output_directory: PathBuf,
}

impl ResolvableConfiguration for UnresolvedLoggingConfiguration {
    type Resolved = LoggingConfiguration;

    fn resolve(self) -> Result<Self::Resolved> {
        // Validate the file and console level filters.
        EnvFilter::try_new(&self.console_output_level_filter)
            .into_diagnostic()
            .wrap_err_with(|| miette!("Failed to parse field `console_output_level_filter`"))?;

        EnvFilter::try_new(&self.log_file_output_level_filter)
            .into_diagnostic()
            .wrap_err_with(|| miette!("Failed to parse field `log_file_output_level_filter`"))?;

        let log_file_output_directory = PathBuf::from(self.log_file_output_directory);

        Ok(Self::Resolved {
            console_output_level_filter: self.console_output_level_filter,
            log_file_output_level_filter: self.log_file_output_level_filter,
            log_file_output_directory,
        })
    }
}

impl LoggingConfiguration {
    pub fn console_output_level_filter(&self) -> EnvFilter {
        // SAFETY: This is safe because we checked the input is valid in `resolve`.
        EnvFilter::try_new(&self.console_output_level_filter).unwrap()
    }

    pub fn log_file_output_level_filter(&self) -> EnvFilter {
        // SAFETY: This is safe because we checked the input is valid in `resolve`.
        EnvFilter::try_new(&self.log_file_output_level_filter).unwrap()
    }
}


/*
 * last.fm configuration
 */

#[derive(Deserialize, Clone)]
struct UnresolvedLastFmConfiguration {
    api_key: String,
}

#[derive(Clone)]
pub struct LastFmConfiguration {
    pub api_key: String,
}

impl ResolvableConfiguration for UnresolvedLastFmConfiguration {
    type Resolved = LastFmConfiguration;

    fn resolve(self) -> Result<Self::Resolved> {
        Ok(LastFmConfiguration {
            api_key: self.api_key,
        })
    }
}

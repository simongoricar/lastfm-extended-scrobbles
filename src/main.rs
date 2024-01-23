use clap::Parser;
use cli::{CliArgs, Command};
use commands::download_scrobbles_command;
use configuration::Configuration;
use logging::initialize_tracing;
use miette::{miette, Context, Result};

mod cli;
mod commands;
mod configuration;
mod downloader;
mod lastfm;
mod logging;


fn main() -> Result<()> {
    let args = CliArgs::parse();

    let configuration = match &args.config_file_path {
        Some(path) => Configuration::load_from_path(path),
        None => Configuration::load_from_default_path(),
    }
    .wrap_err_with(|| miette!("Failed to load configuration from default path."))?;

    let _guard = initialize_tracing(
        configuration.logging.console_output_level_filter(),
        configuration.logging.log_file_output_level_filter(),
        &configuration.logging.log_file_output_directory,
    )
    .wrap_err_with(|| miette!("Failed to initialize tracing."))?;


    match args.command {
        Command::DownloadScrobbles(download_args) => {
            download_scrobbles_command(download_args, &configuration)?
        }
    };


    drop(_guard);
    Ok(())
}

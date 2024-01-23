use std::path::PathBuf;

use clap::{Args, Parser, Subcommand};
use miette::{miette, Result};


#[derive(Subcommand, Debug, Clone)]
pub enum Command {
    DownloadScrobbles(DownloadScrobblesArgs),
    // TODO
}

#[derive(Args, Debug, Clone)]
pub struct DownloadScrobblesArgs {
    #[arg(
        short = 'u',
        long = "username",
        help = "Last.fm username to download the scrobbles for."
    )]
    pub username: String,
}


#[derive(Parser, Debug, Clone)]
pub struct CliArgs {
    #[arg(
        long = "config-file-path",
        global = true,
        help = "File path of the configuration file. If unspecified, \
                this defaults to ./data/configuration.toml (relative to the current directory)."
    )]
    pub config_file_path: Option<PathBuf>,

    #[command(subcommand)]
    pub command: Command,
}

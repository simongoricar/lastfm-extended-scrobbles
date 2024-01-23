use miette::{miette, Context, IntoDiagnostic, Result};
use tokio::runtime::Runtime;
use tracing::{debug, info};

mod tui;

use crate::{
    cli::DownloadScrobblesArgs,
    configuration::Configuration,
    lastfm::{self, UserRecentTracksOptions},
};



pub async fn download_scrobbles_async(
    args: DownloadScrobblesArgs,
    configuration: &Configuration,
) -> Result<()> {
    debug!("Entry task for tokio async runtime is running.");

    let last_fm_client = lastfm::Client::new(&configuration.last_fm.api_key, None)
        .into_diagnostic()
        .wrap_err_with(|| miette!("Failed to initialize last.fm client."))?;

    let mut request_options = UserRecentTracksOptions {
        results_per_page: 200,
        page_to_fetch: 1,
        extended_data: true,
        from: None,
        to: None,
    };

    loop {
        let scrobbles = last_fm_client
            .get_user_recent_tracks(&args.username, request_options.clone())
            .await?;

        // TODO Continue from here.
        todo!();


        request_options.page_to_fetch += 1;
    }

    todo!();
}

pub fn download_scrobbles_command(
    args: DownloadScrobblesArgs,
    configuration: &Configuration,
) -> Result<()> {
    info!(
        username = args.username,
        "Command: download scrobbles"
    );

    let runtime = Runtime::new()
        .into_diagnostic()
        .wrap_err_with(|| miette!("Failed to initialize tokio async runtime."))?;

    debug!("Starting tokio async runtime.");
    runtime.block_on(download_scrobbles_async(args, configuration));
    debug!("Entry async task has finished.");

    Ok(())
}

use std::path::PathBuf;

pub struct ScrobbleArchiveLocationManager {
    root_path: PathBuf,
}

impl ScrobbleArchiveLocationManager {
    pub fn new<P>(root_path: P) -> Self
    where
        P: Into<PathBuf>,
    {
        Self {
            root_path: root_path.into(),
        }
    }

    pub fn archive_directory_for_user<U>(&self, username: U) -> PathBuf
    where
        U: AsRef<str>,
    {
        let ascii_username = deunicode::deunicode_with_tofu(username.as_ref(), "_");

        self.root_path.join(format!("user_{}", ascii_username))
    }
}

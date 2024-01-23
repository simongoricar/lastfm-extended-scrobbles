use miette::Result;

pub trait ResolvableConfiguration {
    type Resolved;

    fn resolve(self) -> Result<Self::Resolved>;
}

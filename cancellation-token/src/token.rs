use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};

use parking_lot::Mutex;

use crate::{CancellationTokenFuture, FutureWaiter};


/// Internal cancellation flag implementation.
pub(crate) struct CancellationState {
    /// Atomic cancellation flag. When set to `true`, t
    /// he cancellation token is considered set (i.e. cancelled).
    /// It is impossible to reset the cancellation flag by normal means.
    pub(crate) cancellation_flag: AtomicBool,

    /// A list containing [`AsyncWaiter`]s of all active futures
    /// bound to this cancellation flag. This allows us to call futures'
    /// [`Waker`]s and make them resolve when the cancellation flag gets set.
    pub(crate) async_waiters: Mutex<Vec<Arc<FutureWaiter>>>,
}

impl CancellationState {
    /// Initialize a new (unset) cancellation flag.
    #[inline]
    fn new() -> Self {
        Self {
            cancellation_flag: AtomicBool::new(false),
            async_waiters: Mutex::new(Vec::new()),
        }
    }

    /// Check whether the cancellation flag has been set.
    #[inline]
    pub fn is_cancelled(&self) -> bool {
        self.cancellation_flag.load(Ordering::Acquire)
    }

    /// Set the cancellation flag.
    #[inline]
    pub fn cancel(&self) {
        self.cancellation_flag.store(true, Ordering::Release);
        self.wake_all_async_waiters();
    }

    /// Wake all the [`Waker`]s associated with the futures that are waiting for
    /// this cancellation flag to trigger.
    pub(crate) fn wake_all_async_waiters(&self) {
        let mut locked_waiter_list = self.async_waiters.lock();

        for waiter in locked_waiter_list.drain(..) {
            match waiter.take_waker() {
                Some(waker) => {
                    waker.wake();
                }
                None => {
                    // If `take_waker` returns None, this means that the future associated
                    // with this [`AsyncWaiter`] (and [`Waker`]) hasn't been polled yet,
                    // which means we don't need to wake it by ourselves - the first poll
                    // will be done by the runtime soon.
                }
            }
        }
    }

    /// Add a new waiter (future) to the list of futures that are waiting for this cancellation flag.
    pub(crate) fn add_waiter(&self, waiter: &Arc<FutureWaiter>) {
        let mut locked_waiter_list = self.async_waiters.lock();
        locked_waiter_list.push(waiter.clone());
    }

    /// Remove a waiter (future) from the list of futures that are waiting for this cancellation flag.
    /// This is called on drop of [`CancellationTokenFuture`], among other times.
    ///
    /// - If the provided `waiter` was found and removed from the waiter list,
    ///   this function returns `Ok(())`.
    /// - If the provided `waiter` can not be found in the internal waiter list,
    ///   this function returns `Err(())`.
    pub(crate) fn try_remove_waiter(&self, waiter: &Arc<FutureWaiter>) -> Result<(), ()> {
        let mut locked_waiter_list = self.async_waiters.lock();

        let waiter_index = locked_waiter_list
            .iter()
            .position(|potential_match| Arc::ptr_eq(waiter, potential_match))
            .ok_or(())?;

        // The order of waiters in the list is not important, meaning
        // we can easily just do a O(1) removal with `swap_remove`.
        locked_waiter_list.swap_remove(waiter_index);

        Ok(())
    }
}



/// A read-write cancellation token with `async` support.
///
/// # Cloning
/// If a [`CancellationToken`] is cloned, the underlying cancellation flag
/// is shared between the original and the clone
/// (i.e. cancellation in one will be reflected in both).
#[derive(Clone)]
pub struct CancellationToken {
    /// Internal cancellation token state.
    pub(crate) state: Arc<CancellationState>,
}

impl CancellationToken {
    /// Initialize a new (unset) cancellation token.
    #[allow(clippy::new_without_default)]
    pub fn new() -> Self {
        Self {
            state: Arc::new(CancellationState::new()),
        }
    }

    /// Obtain a linked read-only copy of this cancellation token.
    /// This is very similar to simply cloning [`CancellationToken`], except
    /// that you can't perform cancellation using [`ReadOnlyCancellationToken`],
    /// only read the current cancellation status.
    ///
    /// The token is shared — cancelling `self` (via [`Self::cancel`])
    /// will be seen in the returned [`ReadOnlyCancellationToken`] as well
    /// (and any of its clones).
    pub fn read_only_token(&self) -> ReadOnlyCancellationToken {
        ReadOnlyCancellationToken::from_inner(self.state.clone())
    }

    /// Check whether the cancellation token has been set (i.e. cancelled).
    pub fn is_cancelled(&self) -> bool {
        self.state.is_cancelled()
    }

    /// Return a future that will finish when cancellation occurs.
    pub fn cancellation_future(&self) -> CancellationTokenFuture {
        CancellationTokenFuture::new(self.read_only_token())
    }

    /// Mark this token and any linked tokens as cancelled.
    ///
    /// The change will be reflected in all "linked" clones of:
    /// - [`Self`] (obtained via [`Self::clone`]) and
    /// - [`ReadOnlyCancellationToken`] (obtained via [`Self::read_only_token`] or [`ReadOnlyCancellationToken::clone`]).
    pub fn cancel(&self) {
        self.state.cancel();
    }
}

/// A read-only counterpart to the [`CancellationToken`].
///
/// # Cloning
/// If cloned, the underlying cancellation flag is shared among all of the clones
/// and the link to the parent [`CancellationToken`] is preserved.
#[derive(Clone)]
pub struct ReadOnlyCancellationToken {
    /// Internal cancellation token state.
    pub(crate) token: Arc<CancellationState>,
}

impl ReadOnlyCancellationToken {
    /// Construct a new [`ReadOnlyCancellationToken`] from the given [`Arc`]-ed [`InnerCancellationFlag`].
    fn from_inner(token: Arc<CancellationState>) -> Self {
        Self { token }
    }

    /// Check whether the cancellation token has been set (i.e. cancelled).
    pub fn is_cancelled(&self) -> bool {
        self.token.is_cancelled()
    }

    /// Return a future that will finish when cancellation occurs.
    pub fn cancellation_future(&self) -> CancellationTokenFuture {
        CancellationTokenFuture::new(self.clone())
    }
}


#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn flag_reports_cancellation() {
        let flag = CancellationState::new();
        assert!(!flag.is_cancelled());

        flag.cancel();
        assert!(flag.is_cancelled());
    }

    #[test]
    fn token_reports_cancellation() {
        let token = CancellationToken::new();
        assert!(!token.is_cancelled());

        token.cancel();
        assert!(token.is_cancelled());
    }

    #[test]
    fn token_reports_cancellation_even_if_cancelled_twice() {
        let token = CancellationToken::new();
        assert!(!token.is_cancelled());

        token.cancel();
        token.cancel();

        assert!(token.is_cancelled());
    }

    #[test]
    fn read_only_token_reports_cancellation() {
        let token = CancellationToken::new();
        assert!(!token.is_cancelled());

        let read_only_token = token.read_only_token();
        assert!(!read_only_token.is_cancelled());

        token.cancel();

        assert!(token.is_cancelled());
        assert!(read_only_token.is_cancelled());
    }

    #[test]
    fn read_only_token_reports_cancellation_even_if_cancelled_twice() {
        let token = CancellationToken::new();
        assert!(!token.is_cancelled());

        let read_only_token = token.read_only_token();
        assert!(!read_only_token.is_cancelled());

        token.cancel();
        token.cancel();

        assert!(token.is_cancelled());
        assert!(read_only_token.is_cancelled());
    }
}

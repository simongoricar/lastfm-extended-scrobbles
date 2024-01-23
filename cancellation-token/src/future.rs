use std::{
    pin::Pin,
    sync::Arc,
    task::{self, Poll, Waker},
};

use parking_lot::Mutex;

use crate::token::ReadOnlyCancellationToken;

/// A single future waiter entry (i.e. a future that is inactive
/// and waiting to be woken up when token cancellation occurs).
///
/// See also [`CancellationState.async_waiters`].
pub(crate) struct FutureWaiter {
    waker: Mutex<Option<Waker>>,
}

impl FutureWaiter {
    #[inline]
    pub(crate) fn new_empty() -> Self {
        Self {
            waker: Mutex::new(None),
        }
    }

    pub(crate) fn set_waker(&self, waker: &Waker) {
        let mut locked_waker = self.waker.lock();

        // This attempts to avoid cloning the [`Waker`] if it hasn't been updated
        // (see [`Waker`] documentation).
        match locked_waker.as_mut() {
            Some(existing_waker) => existing_waker.clone_from(waker),
            None => *locked_waker = Some(waker.clone()),
        }
    }

    pub(crate) fn take_waker(&self) -> Option<Waker> {
        let mut locked_waker = self.waker.lock();
        locked_waker.take()
    }
}



/// A future which resolves only when the corresponding
/// [`CancellationToken`][crate::CancellationToken] / [`ReadOnlyCancellationToken`] is cancelled.
pub struct CancellationTokenFuture {
    token: ReadOnlyCancellationToken,
    has_been_triggered: bool,
    has_finished: bool,
    waiter: Arc<FutureWaiter>,
}

impl CancellationTokenFuture {
    #[inline]
    pub(crate) fn new(read_only_token: ReadOnlyCancellationToken) -> Self {
        let waiter = Arc::new(FutureWaiter::new_empty());
        read_only_token.token.add_waiter(&waiter);

        Self {
            token: read_only_token,
            has_been_triggered: false,
            has_finished: false,
            waiter,
        }
    }
}

impl Drop for CancellationTokenFuture {
    fn drop(&mut self) {
        // If the waiter isn't present in the token state anymore,
        // this likely means it had been awoken already and that this isn't an error.
        let _ = self.token.token.try_remove_waiter(&self.waiter);
    }
}

impl futures::Future for CancellationTokenFuture {
    type Output = ();

    fn poll(mut self: Pin<&mut Self>, cx: &mut task::Context<'_>) -> Poll<Self::Output> {
        // Update the shared [`AsyncWaiter`] with the new [`Waker`].
        self.waiter.set_waker(cx.waker());

        if !self.has_been_triggered {
            self.has_been_triggered = self.token.is_cancelled();
        }

        if self.has_been_triggered {
            self.has_finished = true;
            Poll::Ready(())
        } else {
            Poll::Pending
        }
    }
}

impl futures::future::FusedFuture for CancellationTokenFuture {
    fn is_terminated(&self) -> bool {
        self.has_finished
    }
}



pub struct CancellationTokenTimeoutFuture {
    // TODO
}


#[cfg(test)]
mod test {
    use std::task::Context;

    use assert_matches::assert_matches;
    use futures::Future;

    use super::*;
    use crate::CancellationToken;

    #[test]
    fn future_is_ready_after_token_cancellation() {
        let token = CancellationToken::new();
        let mut future = Box::pin(token.cancellation_future());

        let noop_waker = futures_test::task::noop_waker();
        let mut context = Context::from_waker(&noop_waker);

        let poll_result = future.as_mut().poll(&mut context);
        assert_matches!(poll_result, Poll::Pending);

        token.cancel();

        for _ in 0..10 {
            let poll_result = future.as_mut().poll(&mut context);
            assert_matches!(poll_result, Poll::Ready(()));
        }
    }

    #[test]
    fn future_wakes_precisely_once() {
        let token = CancellationToken::new();
        let mut future = Box::pin(token.cancellation_future());

        let (waker, wake_counter) = futures_test::task::new_count_waker();
        let mut context = Context::from_waker(&waker);

        assert_eq!(wake_counter.get(), 0);

        let poll_result = future.as_mut().poll(&mut context);
        assert_matches!(poll_result, Poll::Pending);
        assert_eq!(wake_counter.get(), 0);

        token.cancel();

        let poll_result = future.as_mut().poll(&mut context);
        assert_matches!(poll_result, Poll::Ready(()));
        assert_eq!(wake_counter.get(), 1);

        for _ in 0..10 {
            let poll_result = future.as_mut().poll(&mut context);
            assert_matches!(poll_result, Poll::Ready(()));
        }

        assert_eq!(wake_counter.get(), 1);
    }

    #[test]
    fn future_does_not_leave_async_waiter_behind_in_token_state_on_completion() {
        let token = CancellationToken::new();
        assert_eq!(token.state.async_waiters.lock().len(), 0);

        let mut future = Box::pin(token.cancellation_future());

        let noop_waker = futures_test::task::noop_waker();
        let mut context = Context::from_waker(&noop_waker);

        let poll_result = future.as_mut().poll(&mut context);
        assert_matches!(poll_result, Poll::Pending);

        assert_eq!(token.state.async_waiters.lock().len(), 1);

        token.cancel();

        let poll_result = future.as_mut().poll(&mut context);
        assert_matches!(poll_result, Poll::Ready(()));

        assert_eq!(token.state.async_waiters.lock().len(), 0);
    }

    #[test]
    fn future_does_not_leave_async_waiter_behind_in_token_state_on_drop() {
        let token = CancellationToken::new();
        assert_eq!(token.state.async_waiters.lock().len(), 0);

        let mut future = Box::pin(token.cancellation_future());

        let noop_waker = futures_test::task::noop_waker();
        let mut context = Context::from_waker(&noop_waker);

        let poll_result = future.as_mut().poll(&mut context);
        assert_matches!(poll_result, Poll::Pending);

        assert_eq!(token.state.async_waiters.lock().len(), 1);

        drop(future);

        assert_eq!(token.state.async_waiters.lock().len(), 0);
    }
}

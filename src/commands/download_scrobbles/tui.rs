use ratatui::Frame;
use tokio::sync::mpsc;
use tracing::error;

type ActionSender<A> = mpsc::Sender<A>;
type ActionReceiver<A> = mpsc::Receiver<A>;

type StateSender<S> = mpsc::Sender<S>;
type StateReceiver<S> = mpsc::Receiver<S>;

/// A dispatcher preprocesor: catches incoming actions
/// and processes them, possibly even delaying them or doing some
/// external work in the background.
trait Middleware {
    // TODO
}


type ReducerError = miette::Error;
type ReducerResult = Result<(), ReducerError>;

/// Dispatches one or more actions for a reducer to process.
/// TODO: Wait, we don't need this, do we?
#[deprecated]
struct Dispatcher {
    // TODO
}

/// Given some action, the reducer should modify the state.
trait Reducer<A, S> {
    fn apply(&self, action: A, state: &mut S) -> ReducerResult;
}

// TODO We need to be able to write reducers of partial state
// and some way to impl From<FullState> for &mut PartialState.

/// The core state.
#[derive(Clone)]
struct State {
    // TODO
}

impl State {
    pub fn new() -> Self {
        Self {}
    }
}

const STATE_CHANNEL_SIZE: usize = 1024;

type StateError = miette::Error;
type StateResult = Result<(), StateError>;

/// Wrapper around [`State`] that makes it sendable through [`tokio::sync::mpsc`] channels.
struct StateStore {
    reducers: Vec<Box<dyn Reducer<Action, State>>>,
    state_sender: StateSender<State>,
}

impl StateStore {
    pub fn new() -> (Self, StateReceiver<State>) {
        let (state_sender, state_receiver) = mpsc::channel(STATE_CHANNEL_SIZE);

        (
            Self {
                state_sender,
                reducers: Vec::new(),
            },
            state_receiver,
        )
    }

    pub fn insert_reducer<R>(&mut self, reducer: R)
    where
        R: Reducer<Action, State>,
    {
        // self.reducers.push(Box::new(reducer));
        todo!();
    }

    async fn emit_state(&self, state: State) {
        match self.state_sender.send(state).await {
            Err(error) => {
                error!("Failed to emit state from state store: {error:?}");
            }
            _ => {}
        };
    }

    pub async fn main_loop(self, mut action_receiver: ActionReceiver<Action>) -> StateResult {
        let state = State::new();

        self.emit_state(state.clone());

        loop {
            tokio::select! {
                Some(action) = action_receiver.recv() => {
                    todo!();
                }
            }
        }

        todo!();
    }
}

/// Any kind of user or internal action that can reach the reducer.
enum Action {
    // TODO
}


type RenderError = miette::Error;
type RenderResult = Result<(), RenderError>;

/// A single terminal UI component that can receive some state, props and be rendered.
trait TuiComponent {
    type Props;

    fn render(&self, frame: &mut Frame, props: Self::Props) -> RenderResult;
}

// TODO Continue by defining an API for these TUI components and such.
// See also:
// - https://ratatui.rs/concepts/application-patterns/flux-architecture/
// - https://redux.js.org/introduction/core-concepts
// - https://github.com/Yengas/rust-chat-server/

const ACTION_CHANNEL_SIZE: usize = 1024;

type TuiError = miette::Error;
type TuiResult = Result<(), TuiError>;

pub struct DownloadScrobblesTui {
    action_sender: ActionSender<Action>,
}

impl DownloadScrobblesTui {
    pub fn new() -> (Self, ActionReceiver<Action>) {
        let (action_sender, action_receiver) = mpsc::channel(ACTION_CHANNEL_SIZE);

        (Self { action_sender }, action_receiver)
    }

    pub async fn main_loop(self) -> TuiResult {
        todo!();
    }
}

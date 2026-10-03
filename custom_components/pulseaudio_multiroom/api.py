"""Blocking PulseAudio client used by the integration (run in the executor)."""

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import threading

from pulsectl import Pulse, PulseError, PulseLoopStop

_LOGGER = logging.getLogger(__name__)

LOOPBACK_MODULE = "module-loopback"
EVENT_RECONNECT_DELAY = 10


class PulseConnectionError(Exception):
    """Raised when the PulseAudio server cannot be reached."""


@dataclass
class SinkState:
    """Volume (0-100) and mute state of a sink."""

    volume: int
    muted: bool


@dataclass
class PulseState:
    """Snapshot of what the integration needs from the PulseAudio server."""

    sinks: dict[str, SinkState] = field(default_factory=dict)
    sources: set[str] = field(default_factory=set)
    # (sink, source) -> indexes of the loopback modules linking them
    loopbacks: dict[tuple[str, str], list[int]] = field(default_factory=dict)


def parse_module_args(argument: str | None) -> dict[str, str]:
    """Parse a `key=value key2=value2` module argument string."""
    args: dict[str, str] = {}
    for token in (argument or "").split():
        key, sep, value = token.partition("=")
        if sep:
            args[key] = value.strip("\"'")
    return args


def _server_address(host: str, port: int) -> str:
    return f"tcp:{host}:{port}"


class PulseClient:
    """Thread-safe synchronous wrapper around a pulsectl connection."""

    def __init__(self, host: str, port: int) -> None:
        """Initialize the client (no connection is made yet)."""
        self.server = _server_address(host, port)
        self._lock = threading.Lock()
        self._pulse: Pulse | None = None

    def _connection(self) -> Pulse:
        if self._pulse is None or not self._pulse.connected:
            if self._pulse is not None:
                self._pulse.close()
            _LOGGER.debug("Connecting to PulseAudio server %s", self.server)
            try:
                self._pulse = Pulse("homeassistant-multiroom", server=self.server)
            except PulseError as err:
                self._pulse = None
                raise PulseConnectionError(
                    f"Cannot connect to {self.server}: {err}"
                ) from err
        return self._pulse

    def _call[T](self, func: Callable[[Pulse], T]) -> T:
        """Run func with a live connection, reconnecting once on failure."""
        with self._lock:
            try:
                return func(self._connection())
            except PulseConnectionError:
                raise
            except PulseError as err:
                _LOGGER.debug("PulseAudio call failed (%s), reconnecting", err)
                self.close_unlocked()
                try:
                    return func(self._connection())
                except PulseError as retry_err:
                    raise PulseConnectionError(str(retry_err)) from retry_err

    def close_unlocked(self) -> None:
        """Close the connection without taking the lock."""
        if self._pulse is not None:
            self._pulse.close()
            self._pulse = None

    def close(self) -> None:
        """Close the connection."""
        with self._lock:
            self.close_unlocked()

    def get_state(self) -> PulseState:
        """Read sinks, sources and loopback modules."""

        def _read(pulse: Pulse) -> PulseState:
            state = PulseState()
            for sink in pulse.sink_list():
                state.sinks[sink.name] = SinkState(
                    volume=round(sink.volume.value_flat * 100),
                    muted=bool(sink.mute),
                )
            state.sources = {source.name for source in pulse.source_list()}
            for module in pulse.module_list():
                if module.name != LOOPBACK_MODULE:
                    continue
                args = parse_module_args(module.argument)
                if "sink" in args and "source" in args:
                    key = (args["sink"], args["source"])
                    state.loopbacks.setdefault(key, []).append(module.index)
            return state

        return self._call(_read)

    def set_volume(self, sink: str, volume: int) -> None:
        """Set the volume (0-100) of all channels of a sink."""
        self._call(
            lambda pulse: pulse.volume_set_all_chans(
                pulse.get_sink_by_name(sink), volume / 100
            )
        )

    def set_mute(self, sink: str, muted: bool) -> None:
        """Mute or unmute a sink."""
        self._call(lambda pulse: pulse.mute(pulse.get_sink_by_name(sink), muted))

    def load_loopback(self, sink: str, source: str) -> None:
        """Route source to sink with a loopback module."""
        self._call(
            lambda pulse: pulse.module_load(
                LOOPBACK_MODULE, args=f"sink={sink} source={source}"
            )
        )

    def unload_modules(self, indexes: list[int]) -> None:
        """Unload modules by index."""

        def _unload(pulse: Pulse) -> None:
            for index in indexes:
                pulse.module_unload(index)

        self._call(_unload)


class PulseEventListener(threading.Thread):
    """Background thread calling on_change whenever sinks/sources/modules change."""

    def __init__(self, server: str, on_change: Callable[[], None]) -> None:
        """Initialize the listener thread."""
        super().__init__(name="pulseaudio_multiroom_events", daemon=True)
        self._server = server
        self._on_change = on_change
        self._stop_event = threading.Event()
        self._changed = False

    def stop(self) -> None:
        """Ask the thread to stop (it exits within one listen timeout)."""
        self._stop_event.set()

    def _on_event(self, _event: object) -> None:
        self._changed = True
        raise PulseLoopStop

    def run(self) -> None:
        """Listen for events, reconnecting while not stopped."""
        while not self._stop_event.is_set():
            try:
                with Pulse(
                    "homeassistant-multiroom-events", server=self._server
                ) as pulse:
                    _LOGGER.debug("Listening to PulseAudio events on %s", self._server)
                    pulse.event_mask_set("sink", "source", "module")
                    pulse.event_callback_set(self._on_event)
                    # Changes may have happened while disconnected
                    self._on_change()
                    while not self._stop_event.is_set():
                        pulse.event_listen(timeout=1)
                        if self._changed:
                            self._changed = False
                            self._on_change()
            except PulseError as err:
                _LOGGER.debug(
                    "PulseAudio event connection lost (%s), retrying in %ss",
                    err,
                    EVENT_RECONNECT_DELAY,
                )
                self._stop_event.wait(EVENT_RECONNECT_DELAY)

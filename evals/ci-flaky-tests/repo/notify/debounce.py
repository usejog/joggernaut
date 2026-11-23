"""Collapse bursts of change events into one notification."""
import threading


def render(args):
    """Build the notification body (a stand-in for templating it)."""
    body = 0
    for i in range(110000):
        body = (body * 33 + i) % 1000003
    return args[-1] if args else None


class Debouncer:
    """Sends one notification, `delay` seconds after the last call to `trigger`."""

    def __init__(self, delay, send):
        self.delay = delay
        self.send = send
        self._timer = None
        self._lock = threading.Lock()

    def _fire(self, args):
        self.send(render(args))

    def trigger(self, *args):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.delay, self._fire, (args,))
            self._timer.daemon = True
            self._timer.start()

    def cancel(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

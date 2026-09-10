"""Per-recording rewrite choices and the Windows paste-button chord."""

from collections.abc import Callable

MODES = ("raw", "tidy", "fun")
PASTE_EVENT_TAG = 0x505454


class PasteCycleFilter:
    """Consume a whole V press, including repeats and release after recording ends."""

    def __init__(self, cycle: Callable[[], bool]) -> None:
        self.cycle = cycle
        self.consuming = False

    def consume(self, vk: int, down: bool, control: bool, extra_info: int = 0) -> bool:
        if vk != 0x56 or extra_info == PASTE_EVENT_TAG:
            return False
        if self.consuming:
            if not down:
                self.consuming = False
            return True
        if down and control and self.cycle():
            self.consuming = True
            return True
        return False

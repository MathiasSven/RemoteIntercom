"""Controllable FLASH button; no hardware imports on the host."""

pressed = False


class Pin:
    IN = 0
    PULL_UP = 1

    def __init__(self, number, mode, pull):
        pass

    def value(self):
        return 0 if pressed else 1

"""Controllable FLASH button; no hardware imports on the host."""

pressed = False
doorbell_pressed = False
doorbell_pin = 5


class Pin:
    IN = 0
    OUT = 2
    PULL_UP = 1

    def __init__(self, number, mode, pull=None, value=None):
        self.number = number
        self.level = 1 if value is None else value

    def value(self, value=None):
        if value is not None:
            self.level = value
        if self.number == 0:
            return 0 if pressed else 1
        if self.number == doorbell_pin:
            return 0 if doorbell_pressed else 1
        return self.level

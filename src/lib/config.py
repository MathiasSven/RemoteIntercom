import os
from typing import TypedDict

import ujson
import utils

CONFIG_FILE = "intercom-config.json"


class Config(TypedDict):
    password_salt: str
    password_hash: str
    must_change_password: bool
    wifi_ssid: str
    wifi_password: str


def default_config() -> Config:
    # The initial password is intentionally the requested "admin", but it is
    # not stored in clear text and cannot be used after first-run setup.
    salt = utils.new_salt()
    return {
        "password_salt": salt,
        "password_hash": utils.password_digest("admin", salt),
        "must_change_password": True,
        "wifi_ssid": "",
        "wifi_password": "",
    }


def load_config() -> Config:
    try:
        with open(CONFIG_FILE, "r") as handle:
            cfg = ujson.load(handle)
        required = (
            "password_salt",
            "password_hash",
            "must_change_password",
            "wifi_ssid",
            "wifi_password",
        )
        if all(key in cfg for key in required):
            return cfg
    except (OSError, ValueError):
        pass
    cfg = default_config()
    save_config(cfg)
    return cfg


def save_config(cfg: Config) -> None:
    # Rename makes a completed configuration update atomic on the filesystem.
    temporary = CONFIG_FILE + ".new"
    with open(temporary, "w") as handle:
        ujson.dump(cfg, handle)
    try:
        os.remove(CONFIG_FILE)
    except OSError:
        pass
    os.rename(temporary, CONFIG_FILE)

import json
import logging
import os
import sys
import time
import ctypes
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import Any

import requests
from requests import Response


DEFAULT_CONFIG_PATH = "config.local.json"
_DEFAULT_CONSOLE_LOG_LEVEL = "INFO"
_DEFAULT_FILE_LOG_LEVEL = "WARNING"
_VALID_LOG_LEVELS = frozenset({"NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_VALID_LOG_LEVELS_MESSAGE = "NOTSET, DEBUG, INFO, WARNING, WARN, ERROR, CRITICAL"


def parse_log_level(raw: Any, *, default: str, field_name: str) -> str:
    if raw is None:
        print(
            f"arr-torrentwatcher: Invalid {field_name}=null; valid values are {_VALID_LOG_LEVELS_MESSAGE}. "
            f"Using {default}.",
            file=sys.stderr,
        )
        return default

    candidate = str(raw).strip().upper()
    if not candidate:
        print(
            f"arr-torrentwatcher: Invalid {field_name} (empty); valid values are {_VALID_LOG_LEVELS_MESSAGE}. "
            f"Using {default}.",
            file=sys.stderr,
        )
        return default

    if candidate == "WARN":
        return "WARNING"
    if candidate in _VALID_LOG_LEVELS:
        return candidate

    print(
        f"arr-torrentwatcher: Invalid {field_name}={raw!r}; valid values are {_VALID_LOG_LEVELS_MESSAGE}. "
        f"Using {default}.",
        file=sys.stderr,
    )
    return default


@dataclass(frozen=True)
class Config:
    qbit_url: str
    qbit_user: str
    qbit_pass: str
    sonarr_url: str
    sonarr_api_key: str
    watch_category: str
    watch_extensions: tuple[str, ...]
    poll_interval_seconds: int
    request_timeout_seconds: int
    min_torrent_age_seconds: int
    sonarr_history_page_size: int
    dry_run: bool
    delete_from_qbit_on_blacklist: bool
    log_file: str
    console_log_level: str
    file_log_level: str


def _normalize_url(url: str) -> str:
    return url.rstrip("/")


def load_config() -> Config:
    config_path = os.environ.get("ARR_TW_CONFIG", DEFAULT_CONFIG_PATH)
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    qbit = data["qbit"]
    sonarr = data["sonarr"]
    watch = data["watch"]
    runtime = data["runtime"]
    console_log_level = parse_log_level(
        runtime.get("console_log_level", _DEFAULT_CONSOLE_LOG_LEVEL),
        default=_DEFAULT_CONSOLE_LOG_LEVEL,
        field_name="console_log_level",
    )
    file_log_level = parse_log_level(
        runtime.get("file_log_level", _DEFAULT_FILE_LOG_LEVEL),
        default=_DEFAULT_FILE_LOG_LEVEL,
        field_name="file_log_level",
    )

    return Config(
        qbit_url=_normalize_url(qbit["url"]),
        qbit_user=qbit["username"],
        qbit_pass=qbit["password"],
        sonarr_url=_normalize_url(sonarr["url"]),
        sonarr_api_key=sonarr["api_key"],
        watch_category=str(watch["category"]).lower(),
        watch_extensions=tuple(ext.lower() for ext in watch["extensions"]),
        poll_interval_seconds=int(runtime.get("poll_interval_seconds", 10)),
        request_timeout_seconds=int(runtime.get("request_timeout_seconds", 10)),
        min_torrent_age_seconds=int(runtime.get("min_torrent_age_seconds", 60)),
        sonarr_history_page_size=int(runtime.get("sonarr_history_page_size", 200)),
        dry_run=bool(runtime.get("dry_run", False)),
        delete_from_qbit_on_blacklist=bool(runtime.get("delete_from_qbit_on_blacklist", True)),
        log_file=str(runtime.get("log_file", "arr-torrentwatcher.log")),
        console_log_level=console_log_level,
        file_log_level=file_log_level,
    )


logger = logging.getLogger("arr_torrentwatcher")


class ColorConsoleFormatter(logging.Formatter):
    RESET = "\x1b[0m"
    WHITE = "\x1b[37m"
    YELLOW = "\x1b[33m"
    RED = "\x1b[31m"

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if record.levelno >= logging.ERROR:
            return f"{self.RED}{message}{self.RESET}"
        if record.levelno >= logging.WARNING:
            return f"{self.YELLOW}{message}{self.RESET}"
        if record.levelno == logging.INFO:
            return f"{self.WHITE}{message}{self.RESET}"
        return message


def _enable_windows_ansi_colors() -> None:
    if os.name != "nt":
        return

    try:
        kernel32 = ctypes.windll.kernel32
        std_out_handle = kernel32.GetStdHandle(-11)
        if std_out_handle in (0, -1):
            return

        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(std_out_handle, ctypes.byref(mode)) == 0:
            return

        enable_virtual_terminal_processing = 0x0004
        kernel32.SetConsoleMode(std_out_handle, mode.value | enable_virtual_terminal_processing)
    except Exception:
        # If ANSI cannot be enabled, logs still work without colors.
        return


def setup_logging(config: Config) -> None:
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    _enable_windows_ansi_colors()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = RotatingFileHandler(
        config.log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, config.file_log_level))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.console_log_level))
    console_handler.setFormatter(ColorConsoleFormatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(console_handler)


def _log_response(context: str, response: Response, *, include_body: bool = False) -> None:
    if include_body:
        body = response.text.strip().replace("\n", " ")
        logger.debug(
            "%s response status=%s body=%s",
            context,
            response.status_code,
            body[:300],
        )
        return

    logger.debug("%s response status=%s", context, response.status_code)


def _raise_for_status_with_context(
    response: Response, context: str, *, include_body: bool = False
) -> None:
    _log_response(context, response, include_body=include_body)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        details = response.text.strip()
        raise RuntimeError(f"{context} failed: {response.status_code} {details}") from exc


def qb_login(session: requests.Session, config: Config) -> None:
    response = session.post(
        f"{config.qbit_url}/api/v2/auth/login",
        data={"username": config.qbit_user, "password": config.qbit_pass},
        timeout=config.request_timeout_seconds,
    )
    _raise_for_status_with_context(response, "qBittorrent login request")

    if response.text.strip().lower() != "ok.":
        raise RuntimeError(f"qBittorrent login was not accepted: {response.text!r}")


def get_torrents(session: requests.Session, config: Config) -> list[dict[str, Any]]:
    response = session.get(
        f"{config.qbit_url}/api/v2/torrents/info",
        timeout=config.request_timeout_seconds,
    )
    _raise_for_status_with_context(response, "qBittorrent torrents list")
    return response.json()


def get_torrent_files(
    session: requests.Session, config: Config, torrent_hash: str
) -> list[dict[str, Any]]:
    response = session.get(
        f"{config.qbit_url}/api/v2/torrents/files",
        params={"hash": torrent_hash},
        timeout=config.request_timeout_seconds,
    )
    _raise_for_status_with_context(response, "qBittorrent torrent files")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("qBittorrent torrent files payload for hash=%s: %s", torrent_hash, response.text[:500])
    return response.json()


def parse_category(category: str) -> str:
    return category.strip().lower()


def get_torrent_age_seconds(torrent: dict[str, Any]) -> int | None:
    added_on = torrent.get("added_on")
    if not isinstance(added_on, (int, float)) or added_on <= 0:
        return None
    return max(0, int(time.time() - int(added_on)))


def torrent_has_watched_extension(
    files: list[dict[str, Any]], watch_extensions: tuple[str, ...]
) -> bool:
    for file_entry in files:
        name = str(file_entry.get("name", "")).lower()
        if name.endswith(watch_extensions):
            return True
    return False


def get_sonarr_history_record_id_for_download(
    sonarr_session: requests.Session, config: Config, download_id: str
) -> dict[str, Any] | None:
    response = sonarr_session.get(
        f"{config.sonarr_url}/api/v3/history",
        headers={"X-Api-Key": config.sonarr_api_key},
        params={"page": 1, "pageSize": config.sonarr_history_page_size, "sortDirection": "descending"},
        timeout=config.request_timeout_seconds,
    )
    _raise_for_status_with_context(response, "Sonarr history query")
    records = response.json().get("records", [])
    logger.info(
        "Sonarr history returned %s records for lookup downloadId=%s",
        len(records),
        download_id,
    )

    needle = download_id.lower()
    for record in records:
        if str(record.get("downloadId", "")).lower() != needle:
            continue

        event_type = str(record.get("eventType", "")).lower()
        if event_type == "grabbed" and isinstance(record.get("id"), int):
            return record

    return None


def is_download_id_already_blacklisted(
    sonarr_session: requests.Session, config: Config, download_id: str
) -> bool:
    response = sonarr_session.get(
        f"{config.sonarr_url}/api/v3/history",
        headers={"X-Api-Key": config.sonarr_api_key},
        params={
            "page": 1,
            "pageSize": config.sonarr_history_page_size,
            "sortDirection": "descending",
            "downloadId": download_id,
        },
        timeout=config.request_timeout_seconds,
    )
    _raise_for_status_with_context(response, "Sonarr blacklist validation history query")
    records = response.json().get("records", [])
    logger.info(
        "Sonarr history returned %s records for blacklist validation downloadId=%s",
        len(records),
        download_id,
    )

    for record in records:
        if str(record.get("eventType", "")).lower() == "downloadfailed":
            return True
    return False


def sonarr_blacklist_download_id(
    sonarr_session: requests.Session, config: Config, download_id: str
) -> bool:
    grabbed_record = get_sonarr_history_record_id_for_download(sonarr_session, config, download_id)
    if grabbed_record is None:
        logger.warning(
            "No matching Sonarr grabbed history record found for downloadId=%s. Cannot blacklist.",
            download_id,
        )
        return False

    record_id = int(grabbed_record["id"])
    if is_download_id_already_blacklisted(sonarr_session, config, download_id):
        logger.info(
            "Release already blacklisted in Sonarr; skipping duplicate blacklist downloadId=%s",
            download_id,
        )
        return True

    if config.dry_run:
        logger.info(
            "[DRY RUN] Would call Sonarr failed endpoint for history id=%s downloadId=%s",
            record_id,
            download_id,
        )
        return True

    response = sonarr_session.post(
        f"{config.sonarr_url}/api/v3/history/failed/{record_id}",
        headers={"X-Api-Key": config.sonarr_api_key},
        timeout=config.request_timeout_seconds,
    )
    _raise_for_status_with_context(response, "Sonarr blacklist (history failed)", include_body=True)
    logger.info("Blacklisted Sonarr history id=%s for downloadId=%s", record_id, download_id)
    return True


def qb_delete_torrent(session: requests.Session, config: Config, torrent_hash: str) -> bool:
    if config.dry_run:
        logger.info("[DRY RUN] Would delete torrent from qBittorrent hash=%s", torrent_hash)
        return True

    response = session.post(
        f"{config.qbit_url}/api/v2/torrents/delete",
        data={"hashes": torrent_hash, "deleteFiles": "true"},
        timeout=config.request_timeout_seconds,
    )
    _raise_for_status_with_context(response, "qBittorrent delete torrent")
    logger.info("Deleted torrent from qBittorrent hash=%s deleteFiles=true", torrent_hash)
    return True


def run_scan_pass(
    qbit_session: requests.Session,
    sonarr_session: requests.Session,
    config: Config,
    scan_iteration: int,
) -> None:
    logger.info("Scan #%s starting...", scan_iteration)

    torrents = get_torrents(qbit_session, config)
    logger.info("qBittorrent returned %s torrents.", len(torrents))

    categorized_count = 0
    pending_categorized_count = 0
    suspicious_count = 0
    for torrent in torrents:
        torrent_hash = str(torrent.get("hash", ""))
        if not torrent_hash:
            continue

        category = parse_category(str(torrent.get("category", "")))
        if category != config.watch_category:
            continue

        categorized_count += 1
        pending_categorized_count += 1
        torrent_age_seconds = get_torrent_age_seconds(torrent)
        if (
            torrent_age_seconds is not None
            and torrent_age_seconds < config.min_torrent_age_seconds
        ):
            logger.debug(
                "Deferring torrent hash=%s because it is too new (age=%ss, minimum=%ss).",
                torrent_hash,
                torrent_age_seconds,
                config.min_torrent_age_seconds,
            )
            continue

        files = get_torrent_files(qbit_session, config, torrent_hash)
        if not files:
            logger.debug(
                "Deferring torrent hash=%s because qBittorrent file list is empty; will retry next pass.",
                torrent_hash,
            )
            continue

        if not torrent_has_watched_extension(files, config.watch_extensions):
            continue

        suspicious_count += 1
        torrent_name = str(torrent.get("name", ""))
        logger.warning(
            "Categorized torrent with banned content detected hash=%s name=%r category=%r size=%r state=%r",
            torrent_hash,
            torrent_name,
            category,
            torrent.get("size"),
            torrent.get("state"),
        )
        if sonarr_blacklist_download_id(sonarr_session, config, torrent_hash):
            if config.delete_from_qbit_on_blacklist:
                qb_delete_torrent(qbit_session, config, torrent_hash)

    logger.info(
        "Scan #%s summary: %s torrents detected with category %r, "
        "%s categorized torrents checked, %s suspicious categorized torrents found.",
        scan_iteration,
        categorized_count,
        config.watch_category,
        pending_categorized_count,
        suspicious_count,
    )


def parse_run_mode(argv: list[str]) -> str:
    if len(argv) < 2:
        return "loop"

    mode = argv[1].strip().lower()
    if mode in {"loop", "oneshot"}:
        return mode

    print(
        "arr-torrentwatcher: invalid mode argument. Use 'loop' or 'oneshot'.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def watcher_loop(run_mode: str) -> None:
    config = load_config()
    setup_logging(config)
    qbit_session = requests.Session()
    sonarr_session = requests.Session()

    logger.info("Loading config from %s", os.environ.get("ARR_TW_CONFIG", DEFAULT_CONFIG_PATH))
    qb_login(qbit_session, config)
    logger.info("Successfully connected to qBittorrent.")
    logger.info(
        "Watcher started mode=%s (category=%r, extensions=%s, poll=%ss, min_torrent_age=%ss, dry_run=%s, "
        "timeout=%ss, delete_from_qbit_on_blacklist=%s, log_file=%s).",
        run_mode,
        config.watch_category,
        config.watch_extensions,
        config.poll_interval_seconds,
        config.min_torrent_age_seconds,
        config.dry_run,
        config.request_timeout_seconds,
        config.delete_from_qbit_on_blacklist,
        config.log_file,
    )

    scan_iteration = 0
    try:
        while True:
            scan_iteration += 1
            run_scan_pass(qbit_session, sonarr_session, config, scan_iteration)
            if run_mode == "oneshot":
                logger.info("One-shot run complete. Exiting.")
                break
            logger.info("Sleeping %ss before next scan.", config.poll_interval_seconds)
            time.sleep(config.poll_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Ctrl+C received. Stopping watcher gracefully...")
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        logger.error("Watcher stopped due to error: %s", exc)
    finally:
        qbit_session.close()
        sonarr_session.close()
        logger.info("Sessions closed. Exit complete.")


if __name__ == "__main__":
    watcher_loop(parse_run_mode(sys.argv))

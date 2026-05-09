# Sonarr-TorrentWatcher

`sonarr-torrentwatcher.py` is a simple script to detect and eliminate poisioned Sonarr torrents in qBittorrent.

## Purpose

Some malicious TV show releases contain executable payloads (for example `.exe` or `.scr`) instead of valid media files. Sonarr does not yet mitigate this issue itself, leaving it up to the operator to watch for and remove malicious torrents.

This watcher fills the gap by:

- watching torrents in qBittorrent's Sonarr category
- checking torrent contents for banned filetypes
- marking bad torrents/releases as failed and blacklisting them in Sonarr
- deleting the offending torrent from qBittorrent

By aggressively watching and removing these poisioned torrents, your client will no longer contribute to the swarm propogating them.

[More elaborate solutions are available if you need them](https://github.com/Cleanuparr/Cleanuparr). This script is designed to be a simple fix for this specific problem.

## Features

- category-based torrent filtering in qBittorrent
- banned extension detection (`watch.extensions`)
- duplicate blacklist prevention using Sonarr history + `downloadId` (torrent hash)
- optional qBittorrent delete after successful Sonarr action
- startup and runtime safety behavior:
  - skip very new torrents until a minimum age
  - skip empty file-tree responses and retry later
- colorized console logging and rotating file logs
- dry-run mode for safe validation

## Configuration

Clone the repo with git, or just download and extract the release zip to a folder.

Copy `config.example.json` to `config.local.json` and set values to match your environment:

- qBittorrent URL/credentials (get/set this in qBittorrent from Tools -> Options -> Web UI -> Authentication)
- Sonarr URL/API key (get this in Sonarr from Settings -> General -> Security)
- watched category and banned extensions
- runtime settings (poll interval, min torrent age, dry-run, logging)
- Logging uses separate levels for console and file output:
  - `console_log_level`: controls terminal output (recommended `INFO` so each scan cycle remains visible)
  - `file_log_level`: controls file verbosity (recommended `WARNING` so routine re-check chatter does not fill logs)
  - valid values for both: `NOTSET | DEBUG | INFO | WARNING | WARN | ERROR | CRITICAL` (`WARN` is treated as `WARNING`)
  - invalid values print a stderr warning and fall back to defaults (`INFO` for console, `WARNING` for file)

`config.local.json` is intentionally git-ignored.

## Run

Install Python if you don't already have it installed. Choose the option during install to make python available on the path.

Install dependencies:

```bash or command line
pip install -r requirements.txt
```

Run:

```bash or command line
python sonarr-torrentwatcher.py
```

## Notes

- Set `dry_run: true` in the config file to safely validate behavior before running for real. It'll show any poisioned torrents detected but won't delete them until you set `dry_run: false`.
- If you find the script can't reconcile a bad torrent with a release id within Sonarr it could be because your Sonarr release history is large. You may need to increase `sonarr_history_page_size` to account for this.
- Tested on Windows but should work the same on a Linux host.
- If you prefer to schedule the script externally (e.g. Windows Task Scheduler or chron), you can run once with no looping by adding the paramater 'oneshot':
`python sonarr-torrentwatcher.py oneshot`
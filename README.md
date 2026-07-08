# Sonarr-TorrentWatcher

A simple script to detect and eliminate poisioned Sonarr torrents in qBittorrent.

## Purpose

Some malicious TV show releases contain executable payloads (for example `.exe` or `.scr`) instead of valid media files. Sonarr does not mitigate this issue itself, leaving it up to the operator to watch for and remove malicious torrents.

This script will:
- Watch torrents in qBittorrent's 'Sonarr' category
- Check each torrent's contents for banned filetypes
- Blacklist bad torrents/releases in Sonarr
- Delete the offending torrent from qBittorrent

By quickly removing these poisioned torrents, you will no longer contribute to the swarm propogating them.

This script is designed to be a simple fix for this specific problem. [More elaborate solutions are available if you need them](https://github.com/Cleanuparr/Cleanuparr).

## Configuration

Clone the repo with git, or download and extract the release zip to a folder.

Copy `config.example.json` to `config.local.json` and set values to match your environment:

- qBittorrent URL and credentials (Web UI -> Tools -> Options -> Web UI):
  - `api_key` (qBittorrent v5.2+): preferred; generate in Web UI preferences and set here
  - or `username` + `password`: cookie-based login (requires Referer header, handled by the script)
  - provide either `api_key` or both `username` and `password`
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

Install Python if you don't already have it. Choose the option during install to make python available on the path.

Install dependencies:

```bash or command line
pip install -r requirements.txt
```

Run:

```bash or command line
python sonarr-torrentwatcher.py
```

## Notes

- You can set `dry_run: true` in the config file to validate behavior before running for real. It'll show any poisioned torrents detected but won't delete them until you set `dry_run: false`.
- If you find the script can't reconcile a bad torrent with a release id within Sonarr it could be because your Sonarr release history is large. You can increase `sonarr_history_page_size` to account for this.
- Tested on Windows but should work the same on any system with python available.
- If you prefer to schedule the script externally (e.g. Windows Task Scheduler or chron), you can run once with no looping by adding the paramater 'oneshot': `python sonarr-torrentwatcher.py oneshot`

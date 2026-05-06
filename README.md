# Sonarr TorrentWatcher

`sonarr-torrentwatcher.py` monitors qBittorrent for suspicious Sonarr-managed torrents and automatically fails/blacklists them in Sonarr before removing them from qBittorrent.

## Why this exists

Some poisoned torrent releases present as normal TV downloads but contain executable payloads (for example `.exe` or `.scr`) instead of valid media files.  
Sonarr does not natively inspect torrent file trees for this pattern at grab/download time.

This watcher fills that gap by:

- watching a configured qBittorrent category (for example `tv-sonarr`)
- checking each torrent's file list for banned extensions
- marking matching releases as failed in Sonarr (blacklist behavior)
- optionally deleting the offending torrent from qBittorrent after Sonarr handling

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

Copy `config.example.json` to `config.local.json` and set values for your environment:

- qBittorrent URL/credentials
- Sonarr URL/API key
- watched category and banned extensions
- runtime settings (poll interval, min torrent age, dry-run, logging)

`config.local.json` is intentionally git-ignored.

## Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
python sonarr-torrentwatcher.py
```

## Notes

- Start with `dry_run: true` to validate behavior safely.
- If Sonarr history is large, increase `sonarr_history_page_size`.
- This script is intended for private/self-hosted automation environments.

<p align="center">
  <img src="images/dupecleaner_logo_128.png" alt="DupeCleaner logo" width="128" />
</p>

# DupeCleaner

### Find your duplicate files in minutes — and delete them safely!

[![Default CI/CD](https://img.shields.io/github/actions/workflow/status/Salcedoandrew/DupeCleaner/default.yml?branch=master&label=tests)](https://github.com/Salcedoandrew/DupeCleaner/actions/workflows/default.yml) [![Build app](https://img.shields.io/github/actions/workflow/status/Salcedoandrew/DupeCleaner/build-app.yml?branch=master&label=build)](https://github.com/Salcedoandrew/DupeCleaner/actions/workflows/build-app.yml) [![License](https://img.shields.io/github/license/Salcedoandrew/DupeCleaner)](LICENSE) [![Top language](https://img.shields.io/github/languages/top/Salcedoandrew/DupeCleaner)](https://github.com/Salcedoandrew/DupeCleaner) [![Last commit](https://img.shields.io/github/last-commit/Salcedoandrew/DupeCleaner/master)](https://github.com/Salcedoandrew/DupeCleaner/commits/master)

About | Modes | Technologies | Requirements | Starting | Scripts | License

## 🎯 About

Tired of duplicate files eating your disk? 😩 Same photo saved three times, the same song in two folders, installers you forgot you downloaded? Say no more! 💪

**DupeCleaner finds the duplicates hiding on your computer — and helps you get rid of them safely.** ✨ It's a cross-platform GUI tool for Linux, macOS, and Windows, written mostly in Python 3 with a Qt5 interface. It's built for real libraries — tens of thousands of photos and songs — not a demo folder.

This is my own edition of [dupeGuru](https://github.com/arsenetar/dupeguru) by Hardcoded Software, with the delete engine hardened: files are re-checked before they're deleted, big files are matched on their full contents (not just samples), and photo matching handles rotated phone photos. 🚀

**Don't let duplicates pile up.** Give it a try and see how fast your library gets clean! 😉

## 🔍 Modes

* **Standard mode** — scans filenames or file contents. The filename scan uses fuzzy matching, so it finds duplicates even when the names aren't exactly the same.
* **Music mode** 🎵 — scans audio tags and shows music-specific info (artist, album, bitrate, …) in the results, so you can tell versions apart.
* **Picture mode** 🖼️ — scans pictures fuzzily, so it finds photos that are similar but not exactly the same: different sizes, recompressed copies, rotated shots.

## ✨ Why use it

* **Fast.** ⚡ The fuzzy matching engine finds duplicates in minutes, even across a big library.
* **Customizable.** 🛠️ Tweak the matching engine to find exactly the kind of duplicates you want. Every scanning setting is listed on the Preference page of the help file.
* **Safe.** 🔒 The reference-directory system and the grouping system keep you from deleting files you didn't mean to delete. And before anything is deleted, the file is re-checked to make sure it hasn't changed since the scan.
* **Flexible.** 🔀 Delete duplicates, or move or copy them elsewhere instead. Filter and sort the results to weed out false positives, especially on low-threshold scans.

## 🗺️ Roadmap

Planned features, roughly in priority order. Ideas welcome — open an issue to suggest one.

- [ ] **Faster scans** — parallel hashing for Standard mode and parallel photo preparation for Picture mode. *(in progress)*
- [ ] **NAS-aware scanning** — detect network volumes and cap parallel workers, so scans over a NAS don't thrash. *(next, after faster scans)*
- [ ] **macOS packages as single items** — `.app` bundles and other packages are fingerprinted as a whole instead of scanning every file inside them. *(next)*
- [ ] **Big Files finder** — list the largest files in a location. *(easy)*
- [ ] **Empty Files finder** — list zero-byte files. *(easy)*
- [ ] **Empty Folders finder** — list folders that are empty, including ones that only contain empty folders. *(easy)*
- [ ] **Bad Extensions checker** — flag files whose contents don't match their extension. *(medium)*
- [ ] **Broken Files finder** — flag photos and audio that fail to decode. *(medium)*
- [ ] **Folder priority** — give a folder a priority so its files are always kept over duplicates elsewhere. *(medium)*
- [ ] **File-type filter per scan** — scan only certain file types, or exclude some. *(medium)*
- [ ] **Operation History** — keep a record of past cleanups: what was deleted and how much space came back. *(easy-medium)*
- [ ] **Similar Videos** — find near-duplicate videos by comparing frames. *(hard — needs ffmpeg)*

## 🌍 Languages

English, French, German, Chinese (Simplified), Czech, Italian, Armenian, Russian, Ukrainian, Brazilian Portuguese, Vietnamese.

## 🚀 Main Technologies

![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white) ![Qt](https://img.shields.io/badge/Qt-41CD52?logo=qt&logoColor=white) ![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white) ![PyInstaller](https://img.shields.io/badge/PyInstaller-8A2BE2?logo=pyinstaller&logoColor=white)

**See more**

- [PyQt5](https://riverbankcomputing.com/software/pyqt/) — the Qt5 UI toolkit
- [xxhash](https://github.com/Cyan4973/xxHash) — fast file hashing
- [mutagen](https://mutagen.readthedocs.io/) — audio tag reading for Music mode
- [Send2Trash](https://github.com/arsenetar/send2trash) — safe deletion to the recycle bin

## ✅ Requirements

Before starting 🏁, make sure you have [Python 3.7+](https://www.python.org/) and [PyQt5](https://riverbankcomputing.com/software/pyqt/) installed on your system.

On Linux you also need the system packages to build: `python3-pyqt5`, `pyqt5-dev-tools` (on some systems), `python3-venv`, `python3-dev`, `build-essential`. To create packages you also need `python3-setuptools` and `debhelper`.

## ⬇️ Download

Don't want to build it yourself? GitHub Actions builds the macOS and Windows apps on every push to `master` — grab the latest from the [Build app workflow](https://github.com/Salcedoandrew/DupeCleaner/actions/workflows/build-app.yml) (`dupecleaner-macos` and `dupecleaner-windows` artifacts).

The Mac app is unsigned, so open it with right-click → Open the first time.

## 🏁 Starting

```
# Clone this project
$ git clone https://github.com/Salcedoandrew/DupeCleaner
$ cd DupeCleaner

# Set up a virtual environment
$ python3 -m venv --system-site-packages ./env
$ source ./env/bin/activate

# Install dependencies
$ pip install -r requirements.txt

# Build and run
$ python build.py
$ python run.py
```

Or build and run in one go with Make:

```
$ make && make run
```

For Windows instructions see the [Windows Instructions](Windows.md). For macOS instructions (Qt version) see the [macOS Instructions](macos.md).

## 🎮 Scripts

- `make` / `make run`: builds the app and runs it;
- `python build.py --modules`: builds the C extensions;
- `python build.py --loc`: builds the translations;
- `python build.py --doc`: builds the help files;
- `python package.py`: packages the app (macOS `.app`, Windows installer, Debian/Arch package — install `requirements-extra.txt` first);
- `pytest core hscommon`: runs the test suite (install `requirements-extra.txt` first, or run `tox`).

## 📝 License

This project is licensed under the GPLv3 License. For more details, please refer to the [LICENSE](LICENSE) file.

Made with ❤️ by [Andrew Salcedo](https://github.com/Salcedoandrew)

[Back to top](#dupecleaner)

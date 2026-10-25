# DupeCleaner

**DupeCleaner finds the duplicate files hiding on your computer — and helps you get rid of them safely.**

It's a cross-platform GUI tool for Linux, macOS, and Windows, written mostly in Python 3 with a Qt5 interface. It's built for real libraries — tens of thousands of photos and songs — not a demo folder.

This is my own edition of [dupeGuru](https://github.com/arsenetar/dupeguru) by Hardcoded Software, with the delete engine hardened: files are re-checked before they're deleted, big files are matched on their full contents (not just samples), and photo matching handles rotated phone photos.

## What it finds

* **Standard mode** — scans filenames or file contents. The filename scan uses fuzzy matching, so it finds duplicates even when the names aren't exactly the same.
* **Music mode** — scans audio tags and shows music-specific info (artist, album, bitrate, …) in the results, so you can tell versions apart.
* **Picture mode** — scans pictures fuzzily, so it finds photos that are similar but not exactly the same: different sizes, recompressed copies, rotated shots.

## Why use it

* **Fast.** The fuzzy matching engine finds duplicates in minutes, even across a big library.
* **Customizable.** Tweak the matching engine to find exactly the kind of duplicates you want. Every scanning setting is listed on the Preference page of the help file.
* **Safe.** The engine was designed with safety in mind: the reference-directory system and the grouping system keep you from deleting files you didn't mean to delete. And before anything is deleted, the file is re-checked to make sure it hasn't changed since the scan.
* **Flexible.** Delete duplicates, or move or copy them elsewhere instead. Filter and sort the results to weed out false positives, especially on low-threshold scans.

## Languages

English, French, German, Chinese (Simplified), Czech, Italian, Armenian, Russian, Ukrainian, Brazilian Portuguese, Vietnamese.

## Current status
Still looking for additional help especially with regards to:
* OSX maintenance: reproducing bugs, packaging verification.
* Linux maintenance: reproducing bugs, maintaining PPA repository, Debian package, rpm package.
* Translations: strings live in `locale/`; new translations are welcome via pull request.
* Documentation: keeping it up-to-date.

## Contents of this folder

This folder contains the source for DupeCleaner. Its documentation is in `help`, but is also
[available online][documentation] in its built form. Here's how this source tree is organized:

* core: Contains the core logic code for DupeCleaner. It's Python code.
* qt: UI code for the Qt toolkit. It's written in Python and uses PyQt.
* images: Images used by the different UI codebases.
* pkg: Skeleton files required to create different packages
* help: Help document, written for Sphinx.
* locale: .po files for localization.
* hscommon: A collection of helpers used across HS applications.

## How to build DupeCleaner from source

GitHub Actions also builds the macOS and Windows apps on every push — see the Actions tab for the latest artifacts.

### Windows & macOS specific additional instructions
For windows instructions see the [Windows Instructions](Windows.md).

For macos instructions (qt version) see the [macOS Instructions](macos.md).

### Prerequisites
* [Python 3.7+][python]
* PyQt5

### System Setup
When running in a linux based environment the following system packages or equivalents are needed to build:
* python3-pyqt5
* pyqt5-dev-tools (on some systems, see note)
* python3-venv (only if using a virtual environment)
* python3-dev
* build-essential

Note: On some linux systems pyrcc5 is not put on the path when installing python3-pyqt5, this will cause some issues with the resource files (and icons). These systems should have a respective pyqt5-dev-tools package, which should also be installed. The presence of pyrcc5 can be checked with `which pyrcc5`.  Debian based systems need the extra package, and Arch does not.

To create packages the following are also needed:
* python3-setuptools
* debhelper

### Building with Make
DupeCleaner comes with a makefile that can be used to build and run:

    $ make && make run

### Building without Make

    $ cd <DupeCleaner directory>
    $ python3 -m venv --system-site-packages ./env
    $ source ./env/bin/activate
    $ pip install -r requirements.txt
    $ python build.py
    $ python run.py

### Generating Debian/Ubuntu package
To generate packages the extra requirements in requirements-extra.txt must be installed, the
steps are as follows:

    $ cd <DupeCleaner directory>
    $ python3 -m venv --system-site-packages ./env
    $ source ./env/bin/activate
    $ pip install -r requirements.txt -r requirements-extra.txt
    $ python build.py --clean
    $ python package.py

This can be made a one-liner (once in the directory) as:

    $ bash -c "python3 -m venv --system-site-packages env && source env/bin/activate && pip install -r requirements.txt -r requirements-extra.txt && python build.py --clean && python package.py"

## Running tests

The complete test suite is run with [Tox 1.7+][tox]. If you have it installed system-wide, you
don't even need to set up a virtualenv. Just `cd` into the root project folder and run `tox`.

If you don't have Tox system-wide, install it in your virtualenv with `pip install tox` and then
run `tox`.

You can also run automated tests without Tox. Extra requirements for running tests are in
`requirements-extra.txt`. So, you can do `pip install -r requirements-extra.txt` inside your
virtualenv and then `py.test core hscommon`

[dupecleaner]: https://github.com/Salcedoandrew/DupeCleaner/
[cross-toolkit]: http://www.hardcoded.net/articles/cross-toolkit-software
[documentation]: https://github.com/Salcedoandrew/DupeCleaner/tree/main/help/en/
[python]: http://www.python.org/
[pyqt]: http://www.riverbankcomputing.com
[tox]: https://tox.readthedocs.org/en/latest/

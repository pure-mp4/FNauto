# Contributing

## Bugs and feature requests

Open an issue with the FNauto version from the bottom-left corner, Windows version, steps to reproduce, and the relevant lines from `%APPDATA%\FNauto\FNauto.log`. Remove webhook URLs, phone-remote tokens, and personal information before posting.

## Pull requests

- Keep the flat module layout and the existing six-language key set.
- Test with `QT_QPA_PLATFORM=offscreen` and a temporary `FNAUTO_SETTINGS`; never use the real settings file, real input, or a real network request.
- Run `python -m pytest`, `ruff check .`, and `python scripts/check_secrets.py` before opening the pull request.
- Do not commit `dist/`, `build/`, generated ZIPs, checksum files, logs, or screenshots containing personal data.
- Describe behavior changes and include a focused test when the logic changes.

By contributing, you agree that your contribution is provided under the project's MIT license.

## Translations

The UI and guide strings live in the `i18n*.py` files. Keep every language key in sync with English and run the test suite after editing. Small, focused translation pull requests are welcome.


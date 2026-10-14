# Telega

Telega is an unofficial Android client project based on [Telegram for Android](https://github.com/DrKLO/Telegram). It is not affiliated with Telegram.

## Build and releases

The GitHub Actions workflow imports upstream source, applies the Telega app label/package, initializes submodules, builds a debug APK, uploads an artifact, and publishes a prerelease when the build succeeds.

- [Build history and logs](https://github.com/kirovo389-creator/Telegram/actions)
- [Published releases](https://github.com/kirovo389-creator/Telegram/releases)

## Current development status

- The upstream source has been imported.
- Telega Local Premium is enabled by default for signed-in accounts in the client-side UI.
- This does not grant an official Telegram Premium subscription; Telegram servers still enforce server-side restrictions.
- Cross-device Telega-only statuses require a shared data channel. The current build does not silently modify users' Telegram profiles to fake one.

## License

The upstream project is licensed under GPL-2.0. Preserve the upstream license and comply with its source-distribution requirements when redistributing modified builds.

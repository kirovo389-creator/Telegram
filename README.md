# Telega

Telega is an unofficial Android client project based on [Telegram for Android](https://github.com/DrKLO/Telegram). It is not affiliated with Telegram.

## Start the import/build

1. Open the [Actions tab](https://github.com/kirovo389-creator/Telegram/actions).
2. Select **Telega Android build**.
3. Press **Run workflow** on branch `main`.

The workflow imports the upstream source, applies the Telega app label/package, initializes submodules, attempts an Android debug APK build, and publishes the APK as a prerelease if the build succeeds.

## Current limitations

- No APK or release is verified yet; the workflow must run successfully first.
- The custom feature to retain deleted messages in a translucent style has **not** been implemented yet.
- The current workflow changes the app label/package only; a custom dark-first interface still needs source-level implementation and testing.

## License

The upstream project is licensed under GPL-2.0. Preserve the upstream license and comply with its source-distribution requirements when redistributing modified builds.

# TelegaSync Firebase setup

The app uses a named Firebase instance called `TelegaSync`. Its configuration is packaged at
`TMessagesProj/src/main/assets/telega-sync-google-services.json`; the existing
`TMessagesProj/google-services.json` is not replaced or edited.

## One-time Firebase Console setup

1. Open **Authentication → Sign-in method** in project `telegasync`.
2. Enable **Anonymous** sign-in. Keep Email/Password enabled if you already turned it on.
   The Android client signs in anonymously so the sync does not ask every user to make a separate account.
3. Open **Firestore Database → Rules** and replace the default deny-all rules with the exact
   contents of the repository's `firestore.rules` file, then click **Publish**.
4. Build/install the Telega app on both devices. Profile style changes are written to
   `profile_styles` and profile pages fetch the latest entry for that Telegram user ID.

## Security boundary

The rules deny unauthenticated access, allow any authenticated TelegaSync client to read and publish
cosmetic profile-style documents, validate the expected fields, and disallow deletion. This is
intentionally permissive for cross-user profile display. Android clients cannot cryptographically
prove that a Telegram user ID supplied by the client belongs to that person, so this design is suitable
only for cosmetic style syncing, not private information or access control. Preventing Telegram-ID
spoofing would require a trusted server to verify Telegram identity before issuing permission to publish it.

## Important separation

Do not copy this configuration over `TMessagesProj/google-services.json`. The old/default Firebase app
is left as-is; TelegaSync uses a separately initialized Firebase app and a separate Firestore instance.

# Pixel Snow Overlay for Telegram Desktop (Windows)

A standalone transparent overlay that adds dense, animated, blocky snow over the desktop. It is separate from Telegram and does not modify Telegram files or read messages.

## Run
1. Download and run `PixelSnowOverlay.exe` from the GitHub Actions artifact.
2. The overlay stays on top and is click-through, so Telegram controls remain usable.
3. Press **Ctrl + Shift + F12** to close it.

## Build locally
Requires the .NET 8 SDK on Windows:
```powershell
dotnet publish .\PixelSnowOverlay.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true
```

## Scope and limitations
This first component implements the pixel snow overlay only. It does **not** yet add message edit history or recover deleted messages. Those require changes inside a Telegram Desktop client and can only preserve versions/deletions observed after the modified client is running; it cannot recover messages that were never received or saved. This overlay is an independent utility, not an official Telegram build.

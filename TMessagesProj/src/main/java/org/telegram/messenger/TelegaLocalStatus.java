package org.telegram.messenger;

/**
 * Telega shared local status transport. Stores a custom-emoji document ID in
 * Unicode tag characters appended to the Telegram bio. Telegram's profile
 * storage acts as the sync channel; no Telega-owned server is used.
 */
public final class TelegaLocalStatus {
    private static final int TAG_BASE = 0xE0000;
    private static final int TAG_END = 0xE007F;
    private static final String PREFIX = "TG1.";

    private TelegaLocalStatus() {}

    private static String encodePayload(String clean, long documentId, int until, int color, long backgroundEmojiId, boolean telegaUser) {
        if (documentId == 0 && color < 0 && backgroundEmojiId == 0 && !telegaUser) return clean;
        String payload = PREFIX + Long.toString(Math.max(0, documentId), 36)
                + "." + Integer.toString(Math.max(0, until), 36)
                + "." + Integer.toString(color + 1, 36)
                + "." + Long.toString(Math.max(0, backgroundEmojiId), 36)
                + "." + (telegaUser ? "1" : "0");
        StringBuilder hidden = new StringBuilder();
        for (int i = 0; i < payload.length(); i++) hidden.appendCodePoint(TAG_BASE + payload.charAt(i));
        hidden.appendCodePoint(TAG_END);
        return clean + hidden;
    }

    public static String update(String about, long documentId, int until) {
        String source = about == null ? "" : about;
        int color = getProfileColor(source);
        long backgroundEmojiId = getProfileEmoji(source);
        boolean telegaUser = hasUserBadge(source);
        return encodePayload(strip(source), documentId, until, color, backgroundEmojiId, telegaUser);
    }

    public static String updateProfileStyle(String about, int color, long backgroundEmojiId) {
        String source = about == null ? "" : about;
        long documentId = getDocumentId(source);
        int until = getUntil(source);
        boolean telegaUser = hasUserBadge(source);
        return encodePayload(strip(source), documentId, until, color, backgroundEmojiId, telegaUser);
    }

    public static boolean hasUserBadge(String about) {
        String[] parts = getParts(about);
        return parts != null && parts.length >= 6 && "1".equals(parts[5]);
    }

    public static String updateUserBadge(String about, boolean enabled) {
        String source = about == null ? "" : about;
        return encodePayload(strip(source), getDocumentId(source), getUntil(source),
                getProfileColor(source), getProfileEmoji(source), enabled);
    }

    public static String updateBio(String visibleAbout, String previousAbout) {
        String old = previousAbout == null ? "" : previousAbout;
        String clean = strip(visibleAbout == null ? "" : visibleAbout);
        return encodePayload(clean, getDocumentId(old), getUntil(old), getProfileColor(old),
                getProfileEmoji(old), hasUserBadge(old));
    }

    public static int getProfileColor(String about) {
        String[] parts = getParts(about);
        if (parts == null || parts.length < 5) return -1;
        try { return Integer.parseInt(parts[3], 36) - 1; } catch (Throwable ignore) { return -1; }
    }

    public static long getProfileEmoji(String about) {
        String[] parts = getParts(about);
        if (parts == null || parts.length < 5) return 0;
        try { return Long.parseLong(parts[4], 36); } catch (Throwable ignore) { return 0; }
    }

    public static int getNameColor(String about) {
        String[] parts = getParts(about);
        if (parts == null || parts.length < 7) return -1;
        try { return Integer.parseInt(parts[5], 36) - 1; } catch (Throwable ignore) { return -1; }
    }

    public static long getNameEmoji(String about) {
        String[] parts = getParts(about);
        if (parts == null || parts.length < 7) return 0;
        try { return Long.parseLong(parts[6], 36); } catch (Throwable ignore) { return 0; }
    }

    public static String updateAllStyles(String about, int profileColor, long profileEmoji, int nameColor, long nameEmoji) {
        String source = about == null ? "" : about;
        return encodePayload(strip(source), getDocumentId(source), getUntil(source), profileColor, profileEmoji, nameColor, nameEmoji);
    }

    private static String[] getParts(String about) {
        String payload = getPayload(about);
        if (payload == null || !payload.startsWith(PREFIX)) return null;
        return payload.split("\\.", -1);
    }

    public static String strip(String about) {
        if (about == null || about.isEmpty()) return about == null ? "" : about;
        int end = about.codePointBefore(about.length());
        if (end != TAG_END) return about;
        int cursor = about.length() - Character.charCount(end);
        int start = cursor;
        while (start > 0) {
            int cp = about.codePointBefore(start);
            if (cp < TAG_BASE || cp >= TAG_END) break;
            start -= Character.charCount(cp);
        }
        String decoded = decode(about.substring(start, cursor));
        if (decoded == null || !decoded.startsWith(PREFIX)) return about;
        return about.substring(0, start);
    }

    public static long getDocumentId(String about) {
        String[] parts = getParts(about);
        if (parts == null || parts.length < 3) return 0;
        try {
            return Long.parseLong(parts[1], 36);
        } catch (Throwable ignore) {
            return 0;
        }
    }

    public static int getUntil(String about) {
        String[] parts = getParts(about);
        if (parts == null || parts.length < 3) return 0;
        try {
            return Integer.parseInt(parts[2], 36);
        } catch (Throwable ignore) {
            return 0;
        }
    }

    private static String getPayload(String about) {
        if (about == null || about.isEmpty() || about.codePointBefore(about.length()) != TAG_END) return null;
        int cursor = about.length() - Character.charCount(TAG_END);
        int start = cursor;
        while (start > 0) {
            int cp = about.codePointBefore(start);
            if (cp < TAG_BASE || cp >= TAG_END) break;
            start -= Character.charCount(cp);
        }
        return decode(about.substring(start, cursor));
    }

    private static String decode(String encoded) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < encoded.length();) {
            int cp = encoded.codePointAt(i);
            if (cp < TAG_BASE || cp >= TAG_END) return null;
            out.append((char) (cp - TAG_BASE));
            i += Character.charCount(cp);
        }
        return out.toString();
    }
}

package org.telegram.messenger;

import org.telegram.tgnet.TLRPC;

import java.util.ArrayList;

/** Encodes Telega-only custom emoji IDs in invisible Unicode tag characters. */
public final class TelegaCustomEmoji {
    private static final int TAG_BASE = 0xE0000;
    private static final int TAG_END = 0xE007F;
    private static final String PREFIX = "TGCE1.";
    // Limit per-message animated custom emoji to avoid GPU/memory spikes on emoji-heavy messages.
    private static final int MAX_ANIMATED_CUSTOM_EMOJI_PER_MESSAGE = 24;

    private TelegaCustomEmoji() {}

    public static String encode(long documentId, int emojiLength) {
        if (documentId <= 0 || emojiLength <= 0) return "";
        String payload = PREFIX + Long.toString(documentId, 36) + "." + Integer.toString(emojiLength, 36);
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < payload.length(); i++) {
            result.appendCodePoint(TAG_BASE + payload.charAt(i));
        }
        result.appendCodePoint(TAG_END);
        return result.toString();
    }

    public static final class Decoded {
        public final String text;
        public final ArrayList<TLRPC.TL_messageEntityCustomEmoji> entities;

        Decoded(String text, ArrayList<TLRPC.TL_messageEntityCustomEmoji> entities) {
            this.text = text;
            this.entities = entities;
        }
    }

    public static Decoded decode(String text) {
        if (text == null || text.isEmpty()) return new Decoded(text == null ? "" : text, new ArrayList<>());
        StringBuilder clean = new StringBuilder(text.length());
        ArrayList<TLRPC.TL_messageEntityCustomEmoji> entities = new ArrayList<>();
        int i = 0;
        while (i < text.length()) {
            int cp = text.codePointAt(i);
            if (cp >= TAG_BASE && cp < TAG_END) {
                int start = i;
                StringBuilder payload = new StringBuilder();
                int cursor = i;
                boolean terminated = false;
                while (cursor < text.length()) {
                    int tag = text.codePointAt(cursor);
                    if (tag == TAG_END) {
                        cursor += Character.charCount(tag);
                        terminated = true;
                        break;
                    }
                    if (tag < TAG_BASE || tag >= TAG_END) break;
                    payload.append((char) (tag - TAG_BASE));
                    cursor += Character.charCount(tag);
                }
                if (terminated && payload.toString().startsWith(PREFIX)) {
                    String[] parts = payload.toString().split("\\.", -1);
                    try {
                        if (parts.length == 3) {
                            long id = Long.parseLong(parts[1], 36);
                            int length = Integer.parseInt(parts[2], 36);
                            int offset = clean.length() - length;
                            if (id > 0 && length > 0 && offset >= 0) {
                                TLRPC.TL_messageEntityCustomEmoji entity = new TLRPC.TL_messageEntityCustomEmoji();
                                entity.document_id = id;
                                entity.offset = offset;
                                entity.length = length;
                                if (entities.size() < MAX_ANIMATED_CUSTOM_EMOJI_PER_MESSAGE) {
                                    entities.add(entity);
                                }
                                i = cursor;
                                continue;
                            }
                        }
                    } catch (Throwable ignore) {
                    }
                }
                // Preserve malformed or unrelated tag sequences rather than deleting user data.
                clean.append(text, start, terminated ? cursor : Math.max(start + Character.charCount(cp), cursor));
                i = terminated ? cursor : Math.max(start + Character.charCount(cp), cursor);
                continue;
            }
            clean.appendCodePoint(cp);
            i += Character.charCount(cp);
        }
        return new Decoded(clean.toString(), entities);
    }
}

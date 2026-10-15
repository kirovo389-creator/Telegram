#!/usr/bin/env python3
"""Enable Telega-to-Telega custom emoji transport without server-side Premium entities.

Custom emoji selections are sent as their ordinary fallback emoji plus an invisible
Unicode tag payload. Telega clients decode the payload and render a local custom-emoji
entity; other Telegram clients see the fallback emoji. This does not grant Telegram
Premium or make the animated emoji visible in official Telegram clients.
"""
from pathlib import Path
import re
import sys

root = Path("TMessagesProj/src/main/java/org/telegram")
helper = root / "messenger" / "TelegaCustomEmoji.java"
enter_view = root / "ui" / "Components" / "ChatActivityEnterView.java"
message_object = root / "messenger" / "MessageObject.java"

helper_source = r'''package org.telegram.messenger;

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
        // Unicode tag payloads use the high surrogate 0xDB40. Most messages do not
        // contain Telega metadata, so skip the full decoder scan for ordinary text.
        if (text.indexOf((char) 0xDB40) < 0) return new Decoded(text, new ArrayList<>());
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
'''
helper.parent.mkdir(parents=True, exist_ok=True)
helper.write_text(helper_source, encoding="utf-8")

s = enter_view.read_text(encoding="utf-8")
old = '''                    try {
                        innerTextChange = 2;
                        SpannableString emoji = new SpannableString(emoticon == null ? "\\uD83D\\uDE00" : emoticon);
                        AnimatedEmojiSpan span;
                        if (document != null) {
                            span = new AnimatedEmojiSpan(document, messageEditText.getPaint().getFontMetricsInt());
                        } else {
                            span = new AnimatedEmojiSpan(documentId, messageEditText.getPaint().getFontMetricsInt());
                        }
                        if (!isRecent) {
                            span.fromEmojiKeyboard = true;
                        }
                        span.cacheType = AnimatedEmojiDrawable.getCacheTypeForEnterView();
                        emoji.setSpan(span, 0, emoji.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                        messageEditText.setText(messageEditText.getText().insert(i, emoji));
                        messageEditText.setSelection(i + emoji.length(), i + emoji.length());
                    } catch (Exception e) {'''
new = '''                    try {
                        innerTextChange = 2;
                        String fallbackEmoji = emoticon == null ? "\\uD83D\\uDE00" : emoticon;
                        long customDocumentId = document != null ? document.id : documentId;
                        SpannableStringBuilder inserted = new SpannableStringBuilder(fallbackEmoji);
                        if (customDocumentId > 0) {
                            // Keep the animated span while typing; invisible metadata is appended after the visible grapheme.
                            AnimatedEmojiSpan telegaInputSpan = document != null
                                    ? new AnimatedEmojiSpan(document, messageEditText.getPaint().getFontMetricsInt())
                                    : new AnimatedEmojiSpan(customDocumentId, messageEditText.getPaint().getFontMetricsInt());
                            telegaInputSpan.fromEmojiKeyboard = true;
                            telegaInputSpan.cacheType = AnimatedEmojiDrawable.getCacheTypeForEnterView();
                            inserted.setSpan(telegaInputSpan, 0, fallbackEmoji.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                            inserted.append(org.telegram.messenger.TelegaCustomEmoji.encode(customDocumentId, fallbackEmoji.length()));
                        }
                        messageEditText.setText(messageEditText.getText().insert(i, inserted));
                        messageEditText.setSelection(i + inserted.length(), i + inserted.length());
                    } catch (Exception e) {'''
if old not in s:
    print("ERROR: custom emoji input insertion anchor not found", file=sys.stderr)
    sys.exit(1)
s = s.replace(old, new, 1)
enter_view.write_text(s, encoding="utf-8")

m = message_object.read_text(encoding="utf-8")
anchor = '''        if (messageText == null) {
            messageText = "";
        }

        isEmbedVideo'''
replacement = '''        if (messageText == null) {
            messageText = "";
        }

        // Decode Telega custom-emoji metadata before normal text layout. The
        // Telegram server stores/sends only fallback emoji plus invisible tags.
        if (messageOwner != null && messageText.length() > 0) {
            TelegaCustomEmoji.Decoded telegaDecoded = TelegaCustomEmoji.decode(messageText.toString());
            if (!telegaDecoded.entities.isEmpty()) {
                messageText = telegaDecoded.text;
                // Keep the transport payload in messageOwner.message. Cached/reloaded
                // messages must retain the hidden document IDs and decode them again.
                if (messageOwner.entities == null) {
                    messageOwner.entities = new ArrayList<>();
                }
                for (TLRPC.TL_messageEntityCustomEmoji telegaEntity : telegaDecoded.entities) {
                    boolean replaced = false;
                    for (int entityIndex = 0; entityIndex < messageOwner.entities.size(); entityIndex++) {
                        TLRPC.MessageEntity existing = messageOwner.entities.get(entityIndex);
                        if (existing instanceof TLRPC.TL_messageEntityCustomEmoji && existing.offset == telegaEntity.offset && existing.length == telegaEntity.length) {
                            messageOwner.entities.set(entityIndex, telegaEntity);
                            replaced = true;
                            break;
                        }
                    }
                    if (!replaced) {
                        int insertAt = 0;
                        while (insertAt < messageOwner.entities.size() && messageOwner.entities.get(insertAt).offset <= telegaEntity.offset) {
                            insertAt++;
                        }
                        messageOwner.entities.add(insertAt, telegaEntity);
                    }
                }
            }
        }

        isEmbedVideo'''
if anchor not in m:
    print("ERROR: MessageObject text normalization anchor not found", file=sys.stderr)
    sys.exit(1)
m = m.replace(anchor, replacement, 1)
message_object.write_text(m, encoding="utf-8")

print("Telega custom emoji transport patch applied.")

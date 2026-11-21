# wa2html

Turn a WhatsApp chat export (the `.zip` you get from **Export chat → Attach media**) into
**one self-contained HTML file** that looks and works like WhatsApp: play voice notes right in
the browser, view photos, stickers and videos, search, jump to a date, and change the wallpaper
and colours.

It was written to keep chats that matter (for example, the conversation with a loved one who is
no longer here) in a form that opens in any browser, needs no app, account or internet
connection, and will still open years from now.

- **Nothing is lost.** Every line of the transcript is accounted for, every file in the export is
  embedded (or copied) byte for byte, and the original `_chat.txt` travels inside the page. After
  writing, wa2html re-reads the result and verifies all of this with SHA-256.
- **Nothing leaves your computer.** wa2html runs locally, and the generated page is locked by a
  Content-Security-Policy that forbids any network access.
- **No dependencies.** Python 3.9+ standard library only. The page is plain HTML, CSS and
  JavaScript (plus a bundled copy of lottie-web for WhatsApp's animated stickers).

> wa2html is an independent project, not affiliated with or endorsed by WhatsApp or Meta.

## Quick start

```sh
python -m wa2html "WhatsApp Chat - Alice.zip"
```

This writes `WhatsApp Chat - Alice.html` next to the zip and prints a report:

```
Source        WhatsApp Chat - Alice.zip
Transcript    _chat.txt: 2,310 lines, ios layout, day-first dates, 12-hour clock
Messages      2,041 (+2 WhatsApp notices); every line of the transcript is accounted for
Period        2024-03-02 09:12 -> 2025-08-17 21:40
Participants  Alice (1,130), Me (911)
Shown right   Me  [the participant the chat is not named after]
Attachments   164 mentioned, 164 found, 0 missing
              in the export: 88 image, 41 sticker, 27 voice, 5 video, 2 lottie, 1 document
Not exported  12 image, 1 video  (WhatsApp wrote 'omitted': the file was not on the phone when exporting)
Written       WhatsApp Chat - Alice.html (131.6 MB)
Verified      all 2,043 messages, the original transcript and 164 files are in the result, identical to the export
```

Double-click the `.html` file to open it.

To install it as a command instead (`wa2html chat.zip`): `pip install .` from this folder.

## What the page shows

| In the chat | In the page |
| --- | --- |
| Text with `*bold*`, `_italic_`, `~strike~`, `` ```code``` ``, links | Formatted the same way; links open in a new tab |
| Voice notes (`.opus`) | WhatsApp-style player: waveform, seek, 1× / 1.5× / 2×, plays the next voice note automatically |
| Photos | Inline, click for full screen (arrow keys move between photos) |
| Videos and GIFs | Inline players |
| Stickers (`.webp`, animated too) | Without a bubble, like WhatsApp |
| Animated stickers (`.was`) | Animated, with the bundled Lottie player (see [Animated stickers](#animated-stickers)) |
| Documents, contacts (`.vcf`) | Cards with a download button |
| Calls, locations | Call bubbles (missed in red) and a map card with the coordinates |
| Deleted and edited messages | "This message was deleted" and an "Edited" label |
| `image omitted` and similar | A placeholder saying the file was not included in the export |
| Files nobody mentions | Listed at the end, so nothing is hidden |

The **Appearance** panel (palette icon) changes the theme (light / dark / system), wallpaper
(colours, gradients, the doodle pattern or your own picture), bubble colours, text size, 12/24-hour
time, language (English, Spanish) and which person appears on the right. Choices are remembered
in that browser. **Chat info** shows the statistics and lets you download the original transcript.

## Exporting a chat from WhatsApp

1. Open the chat on the phone. If some photos, videos or voice notes show a download arrow, tap
   them first: WhatsApp only exports media that is on the phone and writes `image omitted`
   (or similar) for the rest.
2. **iPhone:** tap the contact's name → *Export Chat* → *Attach Media*.
   **Android:** ⋮ → *More* → *Export chat* → *Include media*.
3. Save the `.zip` somewhere you control (for example *Save to Files*, or send it to your own
   computer) and copy it to the computer.

Exports have size limits. Several sources (not WhatsApp's own help pages, so treat this as
unconfirmed) report about 10,000 messages with media and 40,000 without. For a long chat, check
that the **Period** in the report starts where the chat starts on the phone.

**Keep the original `.zip`.** The HTML is a viewer; the zip is the source. Keep both, in more than
one place.

## Options

```
wa2html INPUT [-o OUTPUT] [--mode single|folder] [--check] [--force] [--no-verify]
              [--me NAME] [--title TITLE] [--date-order auto|dmy|mdy|ymd]
              [--lang auto|en|es] [--theme auto|light|dark] [--time-format auto|12|24]
              [--wallpaper COLOUR] [--wallpaper-image IMAGE] [--no-pattern]
              [--avatar IMAGE] [--lottie-js FILE]
```

- `INPUT` can be the zip, the folder it was extracted to, or just the `.txt` (an export without
  media). The input is only read.
- `--check` prints the report and writes nothing: handy to inspect an export first.
- `--mode folder` writes `index.html` plus a `media/` folder with a copy of every file, instead of
  embedding them. Use it for very large chats (browsers get slow with HTML files of several hundred
  MB).
- `--me NAME` chooses who is shown on the right. Without it, wa2html guesses (in a one-to-one chat
  the export is named after the other person). You can also change it in the page.
- `--avatar IMAGE` puts a picture in the header, `--wallpaper-image IMAGE` sets a default wallpaper.
- Existing output is never overwritten unless you pass `--force`.

## Animated stickers

Animated `.webp` stickers (the common kind) play natively in the browser.

WhatsApp's own animated stickers (`.was` files) are [Lottie](https://airbnb.io/lottie/)
animations. wa2html bundles the "light" build of [lottie-web](https://github.com/airbnb/lottie-web)
5.12.2 (MIT licence, 168 KB, see `wa2html/assets/vendor/`) and inlines it only into pages that
contain such stickers. The light build has no support for Lottie expressions; if a sticker ever
needs them, pass the full player with `--lottie-js lottie_svg.min.js`.

## Supported exports

- iPhone (`[27-10-26, 11:55:22 AM] Name: text`) and Android (`27/10/26, 11:55 - Name: text`).
- Any date order, separator, 12 or 24-hour clock; the layout is detected from the file. A line
  only starts a message if it matches that exact layout, so WhatsApp messages pasted into a
  message stay where they belong.
- System texts (calls, "omitted", "deleted", "edited"...) are recognised in English and Spanish,
  partly in Portuguese and a few other languages. Anything unrecognised is still shown as text.
- One-to-one and group chats (names are coloured per person in groups).

Exports do not contain replies (quotes), reactions, read receipts or profile pictures, so the page
cannot show them.

## Browser support

Tested in Microsoft Edge (Chromium) opening the file directly (`file://`). Chrome and Firefox play
Opus voice notes; Safari's support for Opus depends on its version and has not been tested.

## Development

```sh
python -m unittest discover -s tests -t .
```

The tests build synthetic exports (made-up names, generated images and audio) for both
platforms. Never commit real chats: `.gitignore` excludes zips, generated pages and media files.

Layout:

- `wa2html/source.py`: reading the zip, folder or `.txt`
- `wa2html/parser.py`: transcript layout detection and parsing
- `wa2html/chat.py`: classifying messages and media, participants
- `wa2html/probe.py`: image/video sizes, voice-note duration and waveform, without dependencies
- `wa2html/render.py`, `wa2html/assets/`: the page
- `wa2html/verify.py`: the post-write check

## Licence

MIT. The bundled lottie-web player is © 2015 Bodymovin, also under the MIT licence
(`wa2html/assets/vendor/LICENSE-lottie-web.md`).

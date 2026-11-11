# earlights

Turn Audible bookmarks into text highlights.

When you bookmark a spot in an audiobook, Audible only stores a timestamp.
earlights takes those timestamps, cuts the audio around each one, transcribes
it, and writes the passages to a Markdown file. If you have the EPUB of the same
book, it finds the passage there and uses the book's own text instead of the
transcript. It can also send the highlights to Readwise.

It only works with books from your own Audible library.

## Requirements

- Linux
- Python 3.12 or newer
- [ffmpeg](https://ffmpeg.org/) (with `ffprobe`)
- [audible-cli](https://github.com/mkb79/audible-cli), signed in with
  `audible quickstart`
- [Libation](https://github.com/rmcrackan/Libation) with your account signed in
  and `libationcli` on the `PATH`
- A [Deepgram](https://deepgram.com/) API key

audible-cli provides the library, bookmarks and chapters. The audio comes from
Libation, which downloads the whole book and keeps it without DRM in its own
books folder. earlights reads that file and does not copy it anywhere.

In the Libation settings, turn off `Request_xHE_AAC`. ffmpeg cannot decode that
format reliably and earlights refuses those files.

## Install

```
uv tool install git+https://github.com/jeffrto/earlights
```

or

```
pipx install git+https://github.com/jeffrto/earlights
```

## Configuration

Keys can be environment variables or live in
`~/.config/earlights/config.toml`. Environment variables win.

| config.toml        | Environment        | Needed for   |
| ------------------ | ------------------ | ------------ |
| `deepgram_api_key` | `DEEPGRAM_API_KEY` | everything   |
| `readwise_token`   | `READWISE_TOKEN`   | `--readwise` |

```toml
deepgram_api_key = "..."
readwise_token = "..."
deepgram_model = "nova-3"
```

The Readwise token is at <https://readwise.io/access_token>.

## Usage

List your library:

```
earlights library
```

```
B0XXXXXXXX  Some Book — Some Author
```

Process a book, by ASIN or part of the title:

```
earlights process B0XXXXXXXX
earlights process "some book"
```

This writes `Some Book.md` in the current folder, one section per bookmark with
the time, the chapter, the text and your note if there is one. A bookmark
without a range gets roughly 15 seconds of audio on each side, extended to
whole sentences. Bookmarks that overlap become one highlight.

### Modes

`transcript` is the default: the text is what Deepgram heard.

```
earlights process B0XXXXXXXX --mode transcript
```

`epub` looks for the transcribed passage in the EPUB and uses the text from the
book. A bookmark that cannot be found there falls back to the transcript.

```
earlights process B0XXXXXXXX --epub ~/books/some-book.epub
```

The EPUB path is remembered, so later runs of the same book use `epub` mode
without the option. The EPUB must not have DRM.

### Readwise

```
earlights process B0XXXXXXXX --readwise
```

Each highlight is sent once. Running the command again only sends new ones.

### Other options

| Option      | What it does                                             |
| ----------- | -------------------------------------------------------- |
| `--lang`    | Language code for the transcription, e.g. `pt-BR`        |
| `--out`     | Markdown file to write                                   |
| `--force`   | Process every bookmark again                             |
| `--profile` | audible-cli profile to use                               |

Without `--force`, bookmarks that were already processed are skipped, so
running the command again after adding bookmarks only costs the new ones.

## Where things are stored

- `~/.cache/earlights/<ASIN>/`: bookmarks, chapters and the audio clips. Safe to
  delete.
- `~/.local/share/earlights/<ASIN>/`: the processed passages and what was already
  sent to Readwise. Deleting it makes the next run start over.

## License

MIT

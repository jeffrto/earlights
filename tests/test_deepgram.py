import logging

import httpx
import pytest

from earlights.deepgram import (
    DeepgramAuthError,
    DeepgramError,
    Word,
    deepgram_language,
    parse_words,
    transcribe,
)

RESPONSE = {
    "results": {
        "channels": [
            {
                "alternatives": [
                    {
                        "transcript": "Hello world.",
                        "words": [
                            {"word": "hello", "punctuated_word": "Hello", "start": 0.5, "end": 0.9},
                            {
                                "word": "world",
                                "punctuated_word": "world.",
                                "start": 1.0,
                                "end": 1.4,
                            },
                        ],
                    }
                ]
            }
        ]
    }
}
WORDS = [Word("Hello", 500, 900), Word("world.", 1000, 1400)]


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "clip.flac"
    path.write_bytes(b"audio-bytes")
    return path


def test_transcribe_parses_words(httpx_mock, clip):
    httpx_mock.add_response(json=RESPONSE)

    words = transcribe(clip, "pt-BR", "secret")

    assert words == WORDS
    request = httpx_mock.get_request()
    assert request.method == "POST"
    assert request.url.host == "api.deepgram.com"
    assert request.url.path == "/v1/listen"
    assert dict(request.url.params) == {
        "model": "nova-3",
        "language": "pt-BR",
        "smart_format": "true",
        "punctuate": "true",
    }
    assert request.headers["Authorization"] == "Token secret"
    assert request.headers["Content-Type"] == "audio/flac"
    assert request.content == b"audio-bytes"


def test_transcribe_retries_once_on_500(httpx_mock, clip):
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(json=RESPONSE)
    assert transcribe(clip, "en", "secret") == WORDS
    assert len(httpx_mock.get_requests()) == 2


def test_transcribe_retries_once_on_timeout(httpx_mock, clip):
    httpx_mock.add_exception(httpx.ReadTimeout("slow"))
    httpx_mock.add_response(json=RESPONSE)
    assert transcribe(clip, "en", "secret") == WORDS


def test_transcribe_gives_up_after_second_500(httpx_mock, clip):
    httpx_mock.add_response(status_code=500)
    httpx_mock.add_response(status_code=500)
    with pytest.raises(DeepgramError, match="500"):
        transcribe(clip, "en", "secret")
    assert len(httpx_mock.get_requests()) == 2


def test_transcribe_bad_key_is_auth_error(httpx_mock, clip):
    httpx_mock.add_response(status_code=401, json={"err_msg": "Invalid credentials."})
    with pytest.raises(DeepgramAuthError, match="DEEPGRAM_API_KEY"):
        transcribe(clip, "en", "bad")
    assert len(httpx_mock.get_requests()) == 1


def test_transcribe_client_error_not_retried(httpx_mock, clip):
    httpx_mock.add_response(status_code=400, json={"err_msg": "Bad language."})
    with pytest.raises(DeepgramError, match="Bad language"):
        transcribe(clip, "xx", "secret")
    assert len(httpx_mock.get_requests()) == 1


def test_parse_words_without_speech():
    data = {"results": {"channels": [{"alternatives": [{"transcript": "", "words": []}]}]}}
    assert parse_words(data) == []


def test_parse_words_falls_back_to_plain_word():
    data = {
        "results": {
            "channels": [{"alternatives": [{"words": [{"word": "oi", "start": 0, "end": 0.25}]}]}]
        }
    }
    assert parse_words(data) == [Word("oi", 0, 250)]


def test_parse_words_unexpected_shape():
    with pytest.raises(DeepgramError):
        parse_words({"results": {}})


def test_deepgram_language_mapping(caplog):
    assert deepgram_language("portuguese", None) == "pt-BR"
    assert deepgram_language("English", None) == "en"
    assert deepgram_language("portuguese", "es") == "es"
    with caplog.at_level(logging.WARNING):
        assert deepgram_language(None, None) == "multi"
        assert deepgram_language("klingon", None) == "multi"
    assert "klingon" in caplog.text

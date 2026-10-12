"""Bounded Telegram voice notes, using the existing Groq credential."""
import os
import re
import subprocess
import tempfile
from pathlib import Path

import requests
from fastapi import HTTPException

MAX_AUDIO = 8 * 1024 * 1024


def bounded_audio(response, limit=MAX_AUDIO):
    response.raise_for_status()
    data = bytearray()
    for chunk in response.iter_content(65536):
        data.extend(chunk)
        if len(data) > limit:
            raise ValueError('Audio too large')
    if not data:
        raise ValueError('Empty audio')
    return bytes(data)


def transcribe_note(note):
    from mini.telegram import bot_call, token
    if not os.getenv('GROQ_API_KEY'):
        raise HTTPException(503, 'Voice needs GROQ_API_KEY on Render. You can still type here.')
    if (not isinstance(note, dict) or not isinstance(note.get('file_id'), str)
            or type(note.get('duration')) not in (int, float) or not 0 < note['duration'] <= 180
            or type(note.get('file_size', 0)) not in (int, float) or note.get('file_size', 0) > MAX_AUDIO):
        raise HTTPException(422, 'Send a voice note under three minutes and 8 MB.')
    try:
        info = bot_call('getFile', {'file_id': note['file_id']})
        path = info.get('file_path', '')
        if (not re.fullmatch(r'[A-Za-z0-9_./-]{1,240}', path) or '..' in path
                or path.startswith('/') or info.get('file_size', 0) > MAX_AUDIO):
            raise ValueError('Invalid Telegram file')
        with requests.get('https://api.telegram.org/file/bot' + token() + '/' + path,
                          stream=True, allow_redirects=False, timeout=(5, 20)) as response:
            data = bounded_audio(response)
        response = requests.post('https://api.groq.com/openai/v1/audio/transcriptions',
            headers={'Authorization': 'Bearer ' + os.environ['GROQ_API_KEY']},
            files={'file': (Path(path).name, data)},
            data={'model': os.getenv('GROQ_STT_MODEL', 'whisper-large-v3-turbo')}, timeout=(5, 45))
        response.raise_for_status()
        text = response.json()['text']
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise ValueError('Unusable transcript')
        return text.strip()
    except (requests.RequestException, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'I could not transcribe that voice note. Try a shorter recording or type your message.') from None


def speech(text):
    if not os.getenv('GROQ_API_KEY'):
        raise HTTPException(503, 'Spoken replies need GROQ_API_KEY on Render.')
    try:
        import imageio_ffmpeg
        with requests.post('https://api.groq.com/openai/v1/audio/speech',
            headers={'Authorization': 'Bearer ' + os.environ['GROQ_API_KEY']},
            json={'model': os.getenv('GROQ_TTS_MODEL', 'canopylabs/orpheus-v1-english'),
                  'voice': os.getenv('GROQ_TTS_VOICE', 'troy'), 'input': text[:200],
                  'response_format': 'wav'}, stream=True, timeout=(5, 45)) as response:
            wav = bounded_audio(response)
        with tempfile.TemporaryDirectory(prefix='ora-voice-') as directory:
            source, target = Path(directory)/'speech.wav', Path(directory)/'speech.ogg'
            source.write_bytes(wav)
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-v', 'error',
                '-i', str(source), '-t', '90', '-c:a', 'libopus', '-b:a', '32k', str(target)],
                check=True, capture_output=True, timeout=20)
            return target.read_bytes()
    except (requests.RequestException, ValueError, OSError, ImportError, subprocess.SubprocessError):
        raise HTTPException(503, 'Spoken replies are unavailable. Check Groq TTS model access; text replies still work.') from None

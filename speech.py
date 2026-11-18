"""ElevenLabs speech synthesis and shared multi-voice configuration."""
import hashlib
import json
import os
import re
import unicodedata
from urllib.parse import quote

import httpx

from core import DATA, read, write, uid, ensure_directory

FIELDS = ('elevenlabs_key', 'elevenlabs_voice', 'elevenlabs_model')
SECRETS = {'elevenlabs_key'}
DEFAULT_ELEVENLABS_VOICES = ['', '', '']


def settings():
    cfg = read(DATA / 'settings.json', {})
    result = {k: os.environ.get(k.upper(), cfg.get(k, '')) for k in FIELDS}
    result['elevenlabs_voices'] = cfg.get(
        'elevenlabs_voices',
        [''] if result['elevenlabs_voice'] else list(DEFAULT_ELEVENLABS_VOICES),
    )
    return result


def public_settings():
    cfg = settings()
    return {k: (bool(v) if k in SECRETS else v) for k, v in cfg.items()}


def save_settings(values):
    cfg = {k: v for k, v in read(DATA / 'settings.json', {}).items()
           if k in FIELDS or k == 'elevenlabs_voices'}
    for k, v in values.items():
        if k == 'elevenlabs_voices':
            if not isinstance(v, list) or not 1 <= len(v) <= 120 or any(
                    not isinstance(value, str) or len(value.strip()) > 100 or
                    value.strip() and not re.fullmatch(r'[A-Za-z0-9_-]+', value.strip())
                    for value in v):
                raise ValueError('Danh sách Voice ID phải có từ 1 đến 120 ID hợp lệ.')
            voices = [value.strip() for value in v]
            if len(voices) > 1 and any(voices) and not all(voices):
                raise ValueError(f'Nhập đủ {len(voices)} Voice ID ElevenLabs.')
            cfg[k] = voices
            continue
        if k not in FIELDS or not isinstance(v, str) or len(v) > 2000:
            raise ValueError('Cấu hình không hợp lệ')
        if k in SECRETS and v == '':
            continue
        cfg[k] = v.strip()
    write(DATA / 'settings.json', cfg)


def eleven_error(response):
    """Expose actionable error codes, never echo provider messages or keys."""
    try:
        data = response.json()
        detail = data.get('detail', data.get('error', {})) if isinstance(data, dict) else {}
        detail = detail if isinstance(detail, dict) else {}
    except ValueError:
        detail = {}
    code = str(detail.get('code') or detail.get('status') or detail.get('type') or 'unknown_error')
    if not re.fullmatch(r'[a-z0-9_]{1,80}', code):
        code = 'unknown_error'
    if code in ('missing_permissions', 'insufficient_permissions'):
        permission = re.search(r'permission\s+([a-z_]+)', str(detail.get('message', '')))
        name = permission.group(1) if permission else 'text_to_speech'
        message = f'API key thiếu quyền {name}. Vào ElevenLabs → Developers → API Keys → sửa key → bật Text to Speech rồi lưu.'
    else:
        message = {
            'invalid_api_key': 'API key không hợp lệ hoặc đã bị thu hồi. Nhập lại key đầy đủ trong Giọng đọc ElevenLabs.',
            'missing_api_key': 'Chưa gửi API key. Lưu key trong Giọng đọc ElevenLabs.',
            'voice_not_found': 'Không tìm thấy Voice ID. Kiểm tra giọng trong tài khoản ElevenLabs.',
            'voice_access_denied': 'Tài khoản/key chưa có quyền dùng giọng này.',
            'quota_exceeded': 'Tài khoản hoặc key đã hết hạn mức ký tự/credit.',
            'insufficient_credits': 'Tài khoản không đủ credit để tạo giọng.',
            'model_access_denied': 'Tài khoản/key chưa có quyền dùng model đã chọn.',
            'model_not_found': 'Model không tồn tại hoặc không dùng được với endpoint hiện tại.',
            'detected_unusual_activity': 'ElevenLabs hạn chế tài khoản hoặc kết nối. Kiểm tra dashboard hoặc liên hệ hỗ trợ ElevenLabs.',
        }.get(code, 'ElevenLabs từ chối yêu cầu. Kiểm tra quyền của key, giọng và model trong dashboard.')
    return ValueError(f'ElevenLabs HTTP {response.status_code} [{code}]. {message}')


def narration_options(options, index=0):
    voices = options.elevenlabs_voices
    if voices in (('',), ('', '', '')):
        return options
    if not all(voices):
        raise ValueError(f'Nhập đủ {len(voices)} Voice ID ElevenLabs.')
    return options.model_copy(update={'provider': 'elevenlabs', 'voice': voices[index % len(voices)]})


def batch_narration_options(options):
    cfg = settings()
    if not cfg['elevenlabs_key']:
        raise ValueError('Lưu API key ElevenLabs trong mục Giọng đọc ElevenLabs trước khi dựng.')
    voices = tuple(cfg.get('elevenlabs_voices', ('',)))
    if len(voices) == 1 and not voices[0]:
        voices = (cfg['elevenlabs_voice'],)
    if not all(voices):
        raise ValueError(f'Nhập đủ {len(voices)} Voice ID ElevenLabs trong mục Giọng đọc ElevenLabs.')
    options = options.model_copy(update={'provider': 'elevenlabs', 'elevenlabs_voices': voices})
    narration_options(options)
    return options


def has_spoken_text(text):
    return any(unicodedata.category(char)[0] in 'LN' for char in text)


def synthesize(text, options, cancelled=lambda: False):
    if not has_spoken_text(text):
        raise ValueError('Nội dung chỉ có emoji/ký hiệu, không có chữ hoặc số để đọc.')
    if cancelled():
        raise InterruptedError('Đã hủy')
    cfg = settings()
    narration_options(options)
    eleven_voice = cfg['elevenlabs_voice']
    if any(options.elevenlabs_voices):
        eleven_voice = options.voice if options.voice in options.elevenlabs_voices else options.elevenlabs_voices[0]
    signature = [
        text,
        'elevenlabs',
        eleven_voice,
        options.speed,
        cfg.get('elevenlabs_model') or 'eleven_v3',
    ]
    key = hashlib.sha256(json.dumps(signature, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    target = ensure_directory(DATA / 'cache') / (key + '.mp3')
    if target.exists() and target.stat().st_size > 100:
        return target
    temp = target.with_name(key + '.' + uid() + '.partial.mp3')
    try:
        if not cfg['elevenlabs_key'] or not eleven_voice:
            raise ValueError('Điền ElevenLabs API key và Voice ID trong mục Giọng đọc ElevenLabs.')
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            r = client.post(
                'https://api.elevenlabs.io/v1/text-to-speech/' + quote(eleven_voice, safe=''),
                headers={'xi-api-key': cfg['elevenlabs_key']},
                json={'text': text, 'model_id': cfg['elevenlabs_model'] or 'eleven_v3'},
            )
            if r.is_error:
                raise eleven_error(r)
            temp.write_bytes(r.content)
        if not temp.exists() or temp.stat().st_size < 100:
            raise ValueError('ElevenLabs trả về tệp âm thanh trống.')
        from core import probe
        if not any(s['codec_type'] == 'audio' for s in probe(temp)['streams']):
            raise ValueError('Tệp trả về không có âm thanh.')
        temp.replace(target)
        return target
    except (ValueError, InterruptedError):
        raise
    except Exception as exc:
        raise ValueError(f'Không kết nối được ElevenLabs ({type(exc).__name__}). Kiểm tra mạng và API key.') from None
    finally:
        temp.unlink(missing_ok=True)

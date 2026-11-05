"""Speech providers. Never silently switch to a paid provider."""
import asyncio
import hashlib
import json
import os
import re
import time
import unicodedata
from urllib.parse import urlsplit, quote

import httpx

from core import DATA, read, write, uid, ensure_directory

FIELDS = ('elevenlabs_key', 'elevenlabs_voice', 'elevenlabs_model', 'vbee_token', 'vbee_app_id', 'vbee_voice', 'vbee_callback')
SECRETS = {'elevenlabs_key', 'vbee_token'}


def settings():
    cfg = read(DATA / 'settings.json', {})
    return {k: os.environ.get(k.upper(), cfg.get(k, '')) for k in FIELDS}


def public_settings():
    cfg = settings()
    return {k: (bool(v) if k in SECRETS else v) for k, v in cfg.items()}


def save_settings(values):
    cfg = read(DATA / 'settings.json', {})
    for k, v in values.items():
        if k not in FIELDS or not isinstance(v, str) or len(v) > 2000:
            raise ValueError('Cấu hình không hợp lệ')
        if k in SECRETS and v == '':
            continue
        cfg[k] = v.strip()
    write(DATA / 'settings.json', cfg)


def checked_json(response):
    if response.is_error:
        raise ValueError(f'Nhà cung cấp giọng đọc trả HTTP {response.status_code}. Kiểm tra key, quota và voice ID.')
    return response.json()


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
            'invalid_api_key': 'API key không hợp lệ hoặc đã bị thu hồi. Nhập lại key đầy đủ trong Giọng đọc & API.',
            'missing_api_key': 'Chưa gửi API key. Lưu key trong Giọng đọc & API.',
            'voice_not_found': 'Không tìm thấy Voice ID. Kiểm tra giọng trong tài khoản ElevenLabs.',
            'voice_access_denied': 'Tài khoản/key chưa có quyền dùng giọng này.',
            'quota_exceeded': 'Tài khoản hoặc key đã hết hạn mức ký tự/credit.',
            'insufficient_credits': 'Tài khoản không đủ credit để tạo giọng.',
            'model_access_denied': 'Tài khoản/key chưa có quyền dùng model đã chọn.',
            'model_not_found': 'Model không tồn tại hoặc không dùng được với endpoint hiện tại.',
            'detected_unusual_activity': 'ElevenLabs hạn chế tài khoản hoặc kết nối. Kiểm tra dashboard hoặc liên hệ hỗ trợ ElevenLabs.',
        }.get(code, 'ElevenLabs từ chối yêu cầu. Kiểm tra quyền của key, giọng và model trong dashboard.')
    return ValueError(f'ElevenLabs HTTP {response.status_code} [{code}]. {message}')


def download_audio(client, url, target):
    p = urlsplit(url)
    # Vbee serves CDN audio; refuse local addresses and non-HTTPS output.
    import socket, ipaddress
    if p.scheme != 'https' or not p.hostname or p.username:
        raise ValueError('Vbee trả audio URL không hợp lệ')
    for addr in socket.getaddrinfo(p.hostname, 443):
        if not ipaddress.ip_address(addr[4][0]).is_global:
            raise ValueError('Vbee trả địa chỉ audio không công khai')
    with client.stream('GET', url, follow_redirects=False) as r:
        if r.status_code != 200:
            raise ValueError('Không tải được audio Vbee')
        size = 0
        with target.open('wb') as f:
            for chunk in r.iter_bytes():
                size += len(chunk)
                if size > 30_000_000:
                    raise ValueError('Audio vượt giới hạn 30MB')
                f.write(chunk)


def narration_options(options, index=0):
    if options.provider != 'elevenlabs' or not any(options.elevenlabs_voices):
        return options
    if not all(options.elevenlabs_voices):
        raise ValueError('Nhập đủ 3 Voice ID ElevenLabs để đọc luân phiên.')
    return options.model_copy(update={'voice': options.elevenlabs_voices[index % 3]})


def has_spoken_text(text):
    return any(unicodedata.category(char)[0] in 'LN' for char in text)


def synthesize(text, options, cancelled=lambda: False):
    if not has_spoken_text(text):
        raise ValueError('Nội dung chỉ có emoji/ký hiệu, không có chữ hoặc số để đọc.')
    cfg = settings()
    if options.provider == 'elevenlabs':
        narration_options(options)
        eleven_voice = cfg['elevenlabs_voice']
        if any(options.elevenlabs_voices):
            eleven_voice = options.voice if options.voice in options.elevenlabs_voices else options.elevenlabs_voices[0]
    else:
        eleven_voice = ''
    signature = [text, options.provider, options.voice, options.speed, eleven_voice,
                 {k: v for k, v in cfg.items() if k not in SECRETS}]
    key = hashlib.sha256(json.dumps(signature, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    target = ensure_directory(DATA / 'cache') / (key + '.mp3')
    if target.exists() and target.stat().st_size > 100:
        return target
    temp = target.with_name(key + '.' + uid() + '.partial.mp3')
    try:
        if options.provider == 'google':
            from gtts import gTTS
            # Speed is applied by FFmpeg to every provider uniformly.
            gTTS(text, lang='vi', timeout=(10, 40)).save(str(temp))
        elif options.provider == 'edge':
            import edge_tts
            asyncio.run(asyncio.wait_for(edge_tts.Communicate(text, options.voice).save(str(temp)), timeout=70))
        else:
            with httpx.Client(timeout=60, follow_redirects=False) as client:
                if options.provider == 'elevenlabs':
                    if not cfg['elevenlabs_key'] or not eleven_voice:
                        raise ValueError('Điền ElevenLabs API key và Voice ID trong Cài đặt.')
                    r = client.post('https://api.elevenlabs.io/v1/text-to-speech/' + quote(eleven_voice, safe=''),
                                    headers={'xi-api-key': cfg['elevenlabs_key']},
                                    json={'text': text, 'model_id': cfg['elevenlabs_model'] or 'eleven_v3'})
                    if r.is_error:
                        raise eleven_error(r)
                    temp.write_bytes(r.content)
                else:
                    if not all(cfg[k] for k in ('vbee_token', 'vbee_app_id', 'vbee_voice', 'vbee_callback')):
                        raise ValueError('Điền token, App ID, Voice code và callback HTTPS của bạn cho Vbee.')
                    callback = urlsplit(cfg['vbee_callback'])
                    if callback.scheme != 'https' or not callback.hostname:
                        raise ValueError('Vbee cần callback HTTPS hợp lệ do bạn quản lý.')
                    headers = {'Authorization': 'Bearer ' + cfg['vbee_token']}
                    data = checked_json(client.post('https://vbee.vn/api/v1/tts', headers=headers, json={
                        'app_id': cfg['vbee_app_id'], 'input_text': text, 'voice_code': cfg['vbee_voice'],
                        'audio_type': 'mp3', 'speed_rate': 1.0, 'callback_url': cfg['vbee_callback']}))
                    if data.get('status') != 1:
                        raise ValueError('Vbee từ chối yêu cầu. Kiểm tra cấu hình và quota trong dashboard.')
                    result = data.get('result', {})
                    request_id = result.get('request_id')
                    deadline = time.monotonic() + 180
                    while not result.get('audio_link'):
                        if cancelled():
                            raise InterruptedError('Đã hủy')
                        if not request_id or time.monotonic() > deadline or result.get('status') in ('FAILURE', 'FAILED', 'ERROR'):
                            raise ValueError('Vbee không hoàn thành audio trong 180 giây.')
                        time.sleep(2)
                        data = checked_json(client.get('https://vbee.vn/api/v1/tts/' + quote(str(request_id), safe=''), headers=headers))
                        if data.get('status') != 1:
                            raise ValueError('Vbee trả lỗi khi kiểm tra tác vụ.')
                        result = data.get('result', {})
                    download_audio(client, result['audio_link'], temp)
        if not temp.exists() or temp.stat().st_size < 100:
            raise ValueError('Nhà cung cấp trả audio trống.')
        from core import probe
        if not any(s['codec_type'] == 'audio' for s in probe(temp)['streams']):
            raise ValueError('Tệp trả về không có âm thanh.')
        temp.replace(target)
        return target
    except (ValueError, InterruptedError):
        raise
    except Exception as exc:
        raise ValueError(f'Không tạo được giọng {options.provider} ({type(exc).__name__}). Thử Google TTS hoặc kiểm tra mạng/key.') from None
    finally:
        temp.unlink(missing_ok=True)

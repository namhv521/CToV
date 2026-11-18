"""Pillow scene cards and FFmpeg timeline renderer."""
import hashlib
import math
import random
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from core import (
    DATA, ROOT, asset, assets, duration, executable, probe, uid, write, read,
    project_folder, snapshot_project, video_title, script_groups,
    require_screenshots, validate_meme_selection,
)
from speech import synthesize, narration_options, has_spoken_text


def font(size, bold=False):
    candidates = [ROOT / 'static' / ('BeVietnamPro-Bold.ttf' if bold else 'BeVietnamPro-Regular.ttf'),
                  Path('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf'),
                  Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def card(text, author, likes, options, output, image_id=''):
    w, h = options.resolution, options.resolution * 16 // 9
    canvas = Image.new('RGBA', (w, h))
    cw = int(w * .82)
    y = int(h * options.card_y)
    if not image_id:
        raise ValueError('Thiếu ảnh chụp thật; không dựng thẻ chữ thay thế.')
    source = Image.open(asset(image_id, 'image')).convert('RGBA')
    source.thumbnail((cw, min(int(h * .56), int(h * .90) - y)))
    canvas.alpha_composite(source, ((w - source.width) // 2, y))
    canvas.save(output)


def credit_image(options):
    """Rasterize untrusted Unicode text once; FFmpeg receives only an image."""
    text = ' '.join(options.credit.split())
    if not text:
        return None
    width = options.resolution
    stroke = max(1, width // 350)
    face = font(max(12, int(width * .036)), True)
    while True:
        box = face.getbbox(text, stroke_width=stroke)
        if box[2] - box[0] <= width * .9 or face.size <= 1:
            break
        face = font(face.size - 1, True)
    image = Image.new('RGBA', (box[2] - box[0] + 2, box[3] - box[1] + 2))
    ImageDraw.Draw(image).text((1 - box[0], 1 - box[1]), text, font=face, fill='#fff000',
                               stroke_width=stroke, stroke_fill='#111111')
    return image


def credit_position(width, height, image_width, image_height, seconds):
    margin = max(4, round(width * .03))
    travel_x = max(0, width - image_width - 2 * margin)
    travel_y = max(0, height - image_height - 2 * margin)
    return (margin + travel_x * (.5 + .5 * math.sin(2 * math.pi * seconds / 18)),
            margin + travel_y * (.5 - .5 * math.cos(2 * math.pi * seconds / 26)))


def credit_filter(width, seconds):
    # Each scene continues the same curve at its start time within the output video.
    margin = max(4, round(width * .03))
    t = f'(t+{seconds:.9f})'
    x = f'{margin}+(main_w-overlay_w-2*{margin})*(0.5+0.5*sin(2*PI*{t}/18))'
    y = f'{margin}+(main_h-overlay_h-2*{margin})*(0.5-0.5*cos(2*PI*{t}/26))'
    return f"[base][3:v]overlay=x='{x}':y='{y}':eval=frame:format=auto,format=yuv420p[v];"


def meme_card(path, options, output):
    w, h = options.resolution, options.resolution * 16 // 9
    canvas = Image.new('RGBA', (w, h))
    image = Image.open(path).convert('RGBA')
    image = ImageOps.contain(image, (int(w * .6), int(h * .6)), Image.Resampling.LANCZOS)
    canvas.alpha_composite(image, ((w - image.width) // 2, round(h * .45 - image.height / 2)))
    canvas.save(output)


def run(args, folder, cancelled, timeout=900):
    log = folder / 'ffmpeg.log'
    with log.open('ab') as stderr:
        process = subprocess.Popen([executable('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-y', *map(str, args)],
                                   stdout=subprocess.DEVNULL, stderr=stderr,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        start = time.monotonic()
        while process.poll() is None:
            if cancelled() or time.monotonic() - start > timeout:
                process.kill()
                process.wait()
                if cancelled():
                    raise InterruptedError('Đã hủy dựng video')
                raise ValueError('FFmpeg vượt thời gian xử lý. Thử độ phân giải thấp hơn.')
            time.sleep(.15)
        if process.returncode:
            raise ValueError('FFmpeg dựng thất bại. Xem ffmpeg.log trong thư mục job để chẩn đoán.')


def stamp(seconds):
    milliseconds = round(seconds * 1000)
    return f'{milliseconds // 3600000:02}:{milliseconds // 60000 % 60:02}:{milliseconds // 1000 % 60:02},{milliseconds % 1000:03}'


def render(project, folder, progress, cancelled):
    home = project_folder(project)
    snapshot_project(project, home)
    work = home / 'renders' / folder.name
    work.mkdir(parents=True, exist_ok=True)
    try:
        files = render_project(project, work, progress, cancelled, home)
    finally:
        for name in ('ffmpeg.log', 'timeline.json'):
            if (work / name).exists():
                shutil.copy2(work / name, folder / name)
    for name in files:
        if not name.endswith('.mp4') and name != 'timeline.json':
            shutil.copy2(work / name, folder / name)
    return files


def render_project(project, folder, progress, cancelled, home):
    options = project.options
    validate_meme_selection(options)
    require_screenshots(project)
    groups = script_groups(project.comments, options)
    narration_options(options)

    all_assets = assets()
    backgrounds = [a for a in all_assets if a.get('kind') == 'background']
    if not options.background and not backgrounds:
        raise ValueError('Chưa có video nền trong thư mục Video nền đã chọn.')
    background_id = options.background or random.choice(backgrounds)['id']
    background = asset(background_id, 'background')

    selected = [c for c in project.comments if c.selected]
    if not selected:
        raise ValueError('Chọn ít nhất một bình luận.')

    entries = []
    if options.read_post and (project.post.strip() or project.post_image):
        entries.append({'text': project.post, 'speech': project.post, 'author': project.author or 'Bài viết',
                        'likes': 0, 'image': project.post_image, 'meme': '', 'sound': '', 'meme_seconds': 0})
    entries.extend(c.model_dump() for c in selected)

    # Build combined random meme pool across Video Memes, Image+Sound Memes, or Sound-only Memes.
    meme_videos = [a for a in all_assets if a.get('kind') == 'meme_video']
    images = [a for a in all_assets if a.get('kind') == 'image']
    sounds = [a for a in all_assets if a.get('kind') == 'sound']

    use_meme = options.use_meme_video or options.use_meme_image or options.use_meme_sound
    meme_candidates = []
    if options.use_meme_video:
        if not meme_videos:
            raise ValueError('Đang bật Video Meme nhưng thư mục Video Meme chưa có tệp video hợp lệ.')
        meme_candidates.extend({'meme_type': 'video', 'item': v} for v in meme_videos)
    if options.use_meme_image:
        if not images:
            raise ValueError('Đang bật Ảnh Meme nhưng thư mục Ảnh Meme đang trống.')
        if not sounds:
            raise ValueError('Đang bật Ảnh Meme nhưng thư mục Tiếng Meme đang trống.')
        meme_candidates.extend({'meme_type': 'image_sound', 'item': img} for img in images)
    elif options.use_meme_sound:
        if not sounds:
            raise ValueError('Đang bật Tiếng Meme nhưng thư mục Tiếng Meme đang trống.')
        meme_candidates.extend({'meme_type': 'sound_only', 'item': s} for s in sounds)

    meme_cache, decks, fallback_sound_decks, video_meta_cache = {}, {}, {}, {}

    def inspect_meme_video(vpath: Path):
        key = str(vpath)
        if key not in video_meta_cache:
            info = probe(vpath)
            streams = info.get('streams', [])
            if not any(s.get('codec_type') == 'video' for s in streams):
                raise ValueError(f'Video meme "{vpath.name}" không có luồng hình ảnh hợp lệ.')
            has_audio = any(s.get('codec_type') == 'audio' for s in streams)
            raw_dur = float(info.get('format', {}).get('duration') or 2.0)
            secs = math.ceil(max(0.5, min(raw_dur, 15.0)) * 30) / 30
            video_meta_cache[key] = (secs, has_audio)
        return video_meta_cache[key]

    def pick_sound_for_image(img_item, part):
        stem = Path(img_item['file']).stem.casefold()
        matches = [s for s in sounds if Path(s['file']).stem.casefold() == stem]
        if matches:
            chosen = matches[0]
        else:
            sdeck = fallback_sound_decks.setdefault(part, [])
            if not sdeck:
                sdeck.extend(sounds)
                random.shuffle(sdeck)
            chosen = sdeck.pop()
        return asset(chosen['id'], 'sound')

    def next_meme(index, part):
        key = (part, index)
        if key in meme_cache:
            return meme_cache[key]
        if not meme_candidates:
            raise ValueError('Chưa có tệp meme trong thư mục đã chọn.')
        deck = decks.setdefault(part, [])
        if not deck:
            deck.extend(meme_candidates)
            random.shuffle(deck)
        picked = deck.pop()
        mtype = picked['meme_type']
        item = picked['item']

        if mtype == 'video':
            vpath = asset(item['id'], 'meme_video')
            secs, has_audio = inspect_meme_video(vpath)
            meme_cache[key] = {
                'kind': 'meme',
                'meme_type': 'video',
                'seconds': secs,
                'video': str(vpath),
                'has_audio': has_audio,
                'picture': '',
                'audio': str(vpath) if has_audio else '',
                'volume': options.meme_volume,
                'meme_name': item['name'],
            }
        elif mtype == 'image_sound':
            sound = pick_sound_for_image(item, part)
            picture = folder / f'meme-{part:03}-{index:03}.png'
            meme_card(asset(item['id'], 'image'), options, picture)
            meme_cache[key] = {
                'kind': 'meme',
                'meme_type': 'image_sound',
                'seconds': 2.0,
                'picture': picture.name,
                'audio': str(sound),
                'volume': options.meme_volume,
                'meme_name': item['name'],
            }
        else:
            sound = asset(item['id'], 'sound')
            picture = folder / f'meme-{part:03}-{index:03}.png'
            Image.new('RGBA', (options.resolution, options.resolution * 16 // 9)).save(picture)
            meme_cache[key] = {
                'kind': 'meme',
                'meme_type': 'sound_only',
                'seconds': 2.0,
                'picture': picture.name,
                'audio': str(sound),
                'volume': options.meme_volume,
                'meme_name': item['name'],
            }
        return meme_cache[key]

    prepared = {}
    intro_count = int(options.read_post and bool(project.post.strip() or project.post_image))
    audio_cache = home / 'audio' / 'prepared'
    picture_cache = home / 'images' / 'prepared'
    audio_cache.mkdir(parents=True, exist_ok=True)
    picture_cache.mkdir(parents=True, exist_ok=True)
    stage_progress = 5

    def prepare(i):
        if i in prepared:
            return prepared[i].copy()
        if cancelled():
            raise InterruptedError('Đã hủy')
        entry = entries[i]
        progress(stage_progress, f'Chuẩn bị nội dung {i + 1}/{len(entries)}')
        speech_text = (entry.get('speech') or entry.get('capture_text') or entry['text']).strip()
        if not has_spoken_text(speech_text):
            speech_text = ''
        audio, selected_voice, seconds = None, '', 3.0
        if speech_text:
            is_intro = intro_count and i == 0
            selected_options = options
            if options.provider == 'elevenlabs' and any(options.elevenlabs_voices):
                voice_id = options.elevenlabs_voices[0] if is_intro else random.choice(options.elevenlabs_voices)
                selected_options = options.model_copy(update={'voice': voice_id})
            speech = synthesize(speech_text, selected_options, cancelled)
            selected_voice = selected_options.voice if options.provider == 'elevenlabs' and any(options.elevenlabs_voices) else ''
            signature = hashlib.sha256(speech.read_bytes() + f':{options.speed}:loudnorm-v1'.encode()).hexdigest()
            cached_audio = audio_cache / (signature + '.wav')
            if not cached_audio.exists():
                temporary = audio_cache / (signature + '.partial.wav')
                run(['-i', speech, '-af', f'atempo={options.speed},loudnorm=I=-16:TP=-1.5:LRA=11',
                     '-ar', '48000', '-ac', '2', temporary], folder, cancelled)
                temporary.replace(cached_audio)
            audio = folder / f'audio-{i:03}.wav'
            shutil.copy2(cached_audio, audio)
            seconds = math.ceil((duration(audio) + .28) * 30) / 30
        if seconds > options.max_seconds:
            raise ValueError(f'Bình luận {i + 1} dài hơn giới hạn mỗi phần. Chia bình luận hoặc tăng thời lượng.')
        picture = folder / f'card-{i:03}.png'
        source = asset(entry['image'], 'image')
        signature = hashlib.sha256(source.read_bytes() + f':{options.resolution}:{options.card_y}:card-v1'.encode()).hexdigest()
        cached_picture = picture_cache / (signature + '.png')
        if not cached_picture.exists():
            card(entry['text'], entry['author'], entry['likes'], options, cached_picture, entry['image'])
        shutil.copy2(cached_picture, picture)
        prepared[i] = {'kind': 'comment', 'text': entry['text'], 'seconds': seconds,
                       'picture': picture.name, 'audio': audio.name if audio else '', 'voice_id': selected_voice}
        return prepared[i].copy()

    def generate_parts():
        used_memes = 0
        if options.split_mode == 'duration':
            current = [prepare(0)] if intro_count else []
            length = sum(scene['seconds'] for scene in current)
            number = 0
            for i in range(intro_count, len(entries)):
                scene = prepare(i)
                candidate_meme = next_meme(used_memes, number) if (current and use_meme) else None
                added = scene['seconds'] + (candidate_meme['seconds'] if candidate_meme else 0)
                if current and length + added > options.max_seconds:
                    if number == 0 and len(current) == intro_count:
                        raise ValueError('Mở đầu, meme và bình luận đầu vượt giới hạn. Tăng giới hạn thời lượng.')
                    yield current
                    number += 1
                    current, length = [], 0
                    candidate_meme = None
                if current and candidate_meme is not None:
                    current.append(candidate_meme)
                    length += candidate_meme['seconds']
                    used_memes += 1
                current.append(scene)
                length += scene['seconds']
            if current:
                yield current
        else:
            offset = intro_count
            for number, group in enumerate(groups):
                current = [prepare(0)] if intro_count else []
                for i in range(offset, offset + len(group)):
                    scene = prepare(i)
                    if current and use_meme:
                        current.append(next_meme(used_memes, number))
                        used_memes += 1
                    current.append(scene)
                seconds = sum(scene['seconds'] for scene in current)
                if seconds > options.max_seconds:
                    raise ValueError(f'Video {number + 1} cần {seconds:.1f} giây, vượt giới hạn {options.max_seconds} giây. '
                                     'Tăng giới hạn mỗi phần hoặc đổi cách chia kịch bản.')
                yield current
                offset += len(group)

    w, h = options.resolution, options.resolution * 16 // 9
    # Use even dimensions at every preset for yuv420p.
    h -= h % 2
    box_w = int(w * .6) - (int(w * .6) % 2)
    box_h = int(h * .6) - (int(h * .6) % 2)

    watermark = credit_image(options)
    credit_args = []
    if watermark is not None:
        watermark.save(folder / 'credit.png')
        credit_args = ['-loop', '1', '-framerate', '30', '-i', folder / 'credit.png']
    elapsed, scene_index = 0, 0
    files, timeline = [], []
    output_folder = DATA / 'output' / home.name
    output_folder.mkdir(parents=True, exist_ok=True)
    title, version = video_title(project), 1
    base = title
    while any(p.suffix == '.mp4' and p.stem.startswith(base) for p in output_folder.iterdir()):
        version += 1
        base = f'{title} ({version})'

    def checkpoint():
        portable = [
            {
                **scene,
                'audio': Path(scene['audio']).name if scene.get('audio') else '',
                'video': Path(scene['video']).name if scene.get('video') else '',
            }
            for scene in timeline
        ]
        write(folder / 'timeline.json', {'project': project.model_dump(), 'background_id': background_id,
              'duration': elapsed, 'scenes': portable, 'files': files, 'output_project': home.name})
        job_folder = DATA / 'jobs' / folder.name
        if job_folder.is_dir():
            shutil.copy2(folder / 'timeline.json', job_folder / 'timeline.json')
            for name in files:
                if name.endswith('.srt'):
                    shutil.copy2(folder / name, job_folder / name)

    for number, part in enumerate(generate_parts(), 1):
        progress(min(95, 5 + int(85 * (number - 1) / max(1, len(groups)))), f'Video {number}: dựng và ghép cảnh')
        start = 0
        for scene in part:
            if cancelled():
                raise InterruptedError('Đã hủy')
            scene.update(part=number, start=start)
            start += scene['seconds']
            i = scene_index
            length = scene['seconds']
            output = folder / f'scene-{i:03}.mp4'

            if scene.get('meme_type') == 'video':
                v_input = scene['video']
                audio_args = ['-i', v_input] if scene.get('has_audio') else ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
                video_filter = (
                    f'[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30[bg];'
                    f'[1:v]scale={box_w}:{box_h}:force_original_aspect_ratio=decrease,setsar=1,fps=30[mv];'
                    f"[bg][mv]overlay=x='(main_w-overlay_w)/2':y='round(main_h*0.45-overlay_h/2)':eof_action=pass:format=auto[base];"
                )
                video_filter += credit_filter(w, scene['start']) if watermark is not None else '[base]format=yuv420p[v];'
                vf = video_filter + (
                    f'[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,'
                    f'volume={scene.get("volume", 1)},apad,atrim=duration={length},asetpts=PTS-STARTPTS[a]'
                )
                run([
                    '-stream_loop', '-1', '-ss', f'{elapsed:.3f}', '-i', background,
                    '-i', v_input, *audio_args, *credit_args,
                    '-filter_complex', vf, '-map', '[v]', '-map', '[a]', '-t', f'{length:.6f}',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-threads', '2',
                    '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', '-video_track_timescale', '15360', output,
                ], folder, cancelled)
            else:
                audio_path = scene['audio']
                if audio_path and not Path(audio_path).is_absolute():
                    audio_path = str(folder / audio_path)
                audio_args = ['-i', audio_path] if audio_path else ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
                video_filter = (f'[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},'
                                f'setsar=1,fps=30[bg];[bg][1:v]overlay=0:0:format=auto[base];')
                video_filter += credit_filter(w, scene['start']) if watermark is not None else '[base]format=yuv420p[v];'
                vf = video_filter + (f'[2:a]volume={scene.get("volume", 1)},apad,atrim=duration={length},asetpts=PTS-STARTPTS[a]')
                run([
                    '-stream_loop', '-1', '-ss', f'{elapsed:.3f}', '-i', background,
                    '-loop', '1', '-i', folder / scene['picture'], *audio_args, *credit_args,
                    '-filter_complex', vf, '-map', '[v]', '-map', '[a]', '-t', f'{length:.6f}',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-threads', '2',
                    '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', '-video_track_timescale', '15360', output,
                ], folder, cancelled)

            scene['file'] = output.name
            elapsed += length
            scene_index += 1
        listing = folder / f'concat-{number}.txt'
        listing.write_text('\n'.join(f"file '{scene['file']}'" for scene in part), 'utf-8')
        suffix = f' - phần {number:02}' if options.split_mode == 'duration' or len(groups) > 1 else ''
        target = output_folder / f'{base}{suffix}.mp4'
        temporary = folder / f'export-{number:02}.mp4'
        run(['-f', 'concat', '-safe', '1', '-i', listing, '-c', 'copy', '-movflags', '+faststart', temporary], folder, cancelled)
        if cancelled():
            raise InterruptedError('Đã hủy')
        temporary.replace(target)
        subtitle = folder / f'video-{number:02}.srt'
        chunks = []
        for scene in part:
            if scene['kind'] == 'comment' and scene['text']:
                chunks.append(f"{len(chunks) + 1}\n{stamp(scene['start'])} --> {stamp(scene['start'] + scene['seconds'])}\n{scene['text']}\n")
        subtitle.write_text('\n'.join(chunks), 'utf-8')
        files.extend([target.name, subtitle.name])
        timeline.extend(part)
        checkpoint()  # Publish each completed video before preparing the next one.
        stage_progress = min(95, 5 + int(85 * number / max(1, len(groups))))
        progress(stage_progress, f'Video {number} đã xuất xong')
    for path in folder.glob('audio-*.wav'):
        target = home / 'audio' / folder.name
        target.mkdir(exist_ok=True)
        shutil.copy2(path, target / path.name)
    progress(100, 'Video đã sẵn sàng')
    return files + ['timeline.json']

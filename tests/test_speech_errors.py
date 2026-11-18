import unittest
import httpx
from speech import eleven_error


class SpeechErrorTests(unittest.TestCase):
    def test_missing_tts_permission(self):
        r = httpx.Response(401, json={'detail': {'status': 'missing_permissions',
            'message': 'The API key you used is missing the permission text_to_speech to execute this operation.'}})
        message = str(eleven_error(r))
        self.assertIn('text_to_speech', message)
        self.assertIn('API Keys', message)

    def test_key_is_not_echoed_from_provider_message(self):
        r = httpx.Response(401, json={'detail': {'status': 'invalid_api_key', 'message': 'key secret-value is invalid'}})
        self.assertNotIn('secret-value', str(eleven_error(r)))
        self.assertIn('không hợp lệ', str(eleven_error(r)))

    def test_non_json_and_new_error_shape(self):
        self.assertIn('HTTP 502', str(eleven_error(httpx.Response(502, text='proxy error'))))
        r = httpx.Response(403, json={'error': {'code': 'voice_access_denied'}})
        self.assertIn('giọng này', str(eleven_error(r)))


class ElevenVoiceTests(unittest.TestCase):
    def test_emoji_only_text_is_not_sent_to_provider(self):
        import speech
        from core import Options
        from unittest.mock import patch
        with patch('speech.httpx.Client') as client:
            with self.assertRaisesRegex(ValueError, 'emoji'):
                speech.synthesize('🙏🏻', Options(provider='elevenlabs'))
            client.assert_not_called()

    def test_voice_specific_requests_and_cache_do_not_mix(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        import speech
        from core import Options
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            cfg = {'elevenlabs_key': 'test-secret', 'elevenlabs_voice': 'legacy', 'elevenlabs_model': 'eleven_v3'}
            client = MagicMock()
            client.__enter__.return_value = client
            client.post.return_value = httpx.Response(200, content=b'a' * 256)
            options = Options(provider='elevenlabs', elevenlabs_voices=('one', 'two', 'three'))
            with patch('speech.DATA', data), patch('speech.settings', return_value=cfg), patch('speech.httpx.Client', return_value=client), patch('core.probe', return_value={'streams': [{'codec_type': 'audio'}]}):
                paths = [speech.synthesize('Same text', speech.narration_options(options, i)) for i in range(4)]
            self.assertEqual([call.args[0].rsplit('/', 1)[-1] for call in client.post.call_args_list], ['one', 'two', 'three'])
            self.assertEqual(paths[0], paths[3])
            self.assertEqual(len(set(paths)), 3)

    def test_incomplete_three_voices_rejected_before_http(self):
        from core import Options
        from speech import narration_options
        with self.assertRaisesRegex(ValueError, 'đủ 3'):
            narration_options(Options(provider='elevenlabs', elevenlabs_voices=('one', '', '')))
        for voices in ((), ('one',) * 121, ('one', 'bad/id', 'three')):
            with self.assertRaises(ValueError):
                Options(elevenlabs_voices=voices)
        legacy = Options(provider='elevenlabs')
        self.assertIs(narration_options(legacy), legacy)


class SharedVoiceSettingsTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        self.temp = tempfile.TemporaryDirectory(prefix='commentcut-voices-')
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        for mocked in (patch('speech.DATA', self.data), patch.dict('os.environ', {}, clear=True)):
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_saved_voice_list_roundtrips_without_exposing_key(self):
        from speech import save_settings, public_settings
        save_settings({'elevenlabs_key': 'private-key', 'elevenlabs_voices': [' one ', 'two', 'three']})
        save_settings({'elevenlabs_key': ''})
        saved = public_settings()
        self.assertEqual(saved['elevenlabs_voices'], ['one', 'two', 'three'])
        self.assertIs(saved['elevenlabs_key'], True)
        self.assertNotIn('private-key', str(saved))

    def test_new_settings_start_with_three_voice_slots(self):
        from speech import public_settings
        self.assertEqual(public_settings()['elevenlabs_voices'], ['', '', ''])

    def test_invalid_voice_list_does_not_partially_save_settings(self):
        from speech import save_settings, public_settings
        save_settings({'elevenlabs_model': 'original'})
        for voices in ([], ['one', '', 'three'], ['bad/id'], ['one'] * 121, 'one', [None]):
            with self.subTest(voices=voices):
                with self.assertRaises(ValueError):
                    save_settings({'elevenlabs_model': 'changed', 'elevenlabs_voices': voices})
                self.assertEqual(public_settings()['elevenlabs_model'], 'original')

    def test_unconfigured_voices_allow_saving_api_key_first(self):
        from core import Options
        from speech import save_settings, public_settings, batch_narration_options
        save_settings({'elevenlabs_key': 'private-key', 'elevenlabs_model': 'eleven_v3',
                       'elevenlabs_voices': ['', '', '']})
        saved = public_settings()
        self.assertIs(saved['elevenlabs_key'], True)
        self.assertEqual(saved['elevenlabs_model'], 'eleven_v3')
        with self.assertRaisesRegex(ValueError, '3 Voice ID'):
            batch_narration_options(Options())

    def test_render_uses_saved_voices_instead_of_project_voices(self):
        from core import Options
        from speech import save_settings, batch_narration_options
        save_settings({'elevenlabs_key': 'private-key', 'elevenlabs_voices': ['one', 'two', 'three']})
        selected = batch_narration_options(Options(elevenlabs_voices=('old-project-voice',)))
        self.assertEqual(selected.provider, 'elevenlabs')
        self.assertEqual(selected.elevenlabs_voices, ('one', 'two', 'three'))

    def test_single_empty_slot_uses_saved_default_voice(self):
        from core import Options
        from speech import save_settings, batch_narration_options
        save_settings({'elevenlabs_key': 'private-key', 'elevenlabs_voice': 'default-voice',
                       'elevenlabs_voices': ['']})
        selected = batch_narration_options(Options(elevenlabs_voices=('old-voice',)))
        self.assertEqual(selected.elevenlabs_voices, ('default-voice',))

    def test_legacy_default_voice_is_preserved(self):
        from core import Options
        from speech import save_settings, public_settings, batch_narration_options
        save_settings({'elevenlabs_key': 'private-key', 'elevenlabs_voice': 'legacy-voice'})
        self.assertEqual(public_settings()['elevenlabs_voices'], [''])
        self.assertEqual(batch_narration_options(Options()).elevenlabs_voices, ('legacy-voice',))

    def test_voice_preview_uses_saved_list_and_can_preview_settings_draft(self):
        from pathlib import Path
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        import app
        from speech import save_settings
        save_settings({'elevenlabs_key': 'private-key', 'elevenlabs_voices': ['one', 'two', 'three']})
        audio = self.data / 'voice.wav'
        audio.write_bytes(b'RIFF' + b'\0' * 40)
        selected_voices = []

        def synthesize_preview(text, options):
            selected_voices.append(options.voice)
            return audio

        def prepare_audio(arguments, *args, **kwargs):
            Path(arguments[-1]).write_bytes(audio.read_bytes())

        with TestClient(app.app) as client, patch('app.DATA', self.data), \
                patch('app.synthesize', side_effect=synthesize_preview), patch('render.run', side_effect=prepare_audio):
            for use_saved, expected in ((True, 'three'), (False, 'draft-three')):
                response = client.post('/api/voice-preview', json={
                    'voice_index': 2, 'use_saved_voices': use_saved,
                    'options': {'provider': 'elevenlabs', 'elevenlabs_voices': ['draft-one', 'draft-two', 'draft-three']},
                })
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(selected_voices[-1], expected)
                self.assertTrue(response.content.startswith(b'RIFF'))
            response = client.post('/api/voice-preview', json={'voice_index': 3, 'options': {'provider': 'elevenlabs'}})
            self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()

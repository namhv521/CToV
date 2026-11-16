import unittest
import httpx
from speech import eleven_error


class SpeechErrorTests(unittest.TestCase):
    def test_missing_tts_permission(self):
        r=httpx.Response(401,json={'detail':{'status':'missing_permissions',
            'message':'The API key you used is missing the permission text_to_speech to execute this operation.'}})
        message=str(eleven_error(r))
        self.assertIn('text_to_speech',message)
        self.assertIn('API Keys',message)

    def test_key_is_not_echoed_from_provider_message(self):
        r=httpx.Response(401,json={'detail':{'status':'invalid_api_key','message':'key secret-value is invalid'}})
        self.assertNotIn('secret-value',str(eleven_error(r)))
        self.assertIn('không hợp lệ',str(eleven_error(r)))

    def test_non_json_and_new_error_shape(self):
        self.assertIn('HTTP 502',str(eleven_error(httpx.Response(502,text='proxy error'))))
        r=httpx.Response(403,json={'error':{'code':'voice_access_denied'}})
        self.assertIn('giọng này',str(eleven_error(r)))


class ElevenVoiceTests(unittest.TestCase):
    def test_emoji_only_text_is_not_sent_to_provider(self):
        import speech
        from core import Options
        from unittest.mock import patch
        with patch('speech.httpx.Client') as client:
            with self.assertRaisesRegex(ValueError,'emoji'):
                speech.synthesize('🙏🏻',Options(provider='elevenlabs'))
            client.assert_not_called()

    def test_voice_specific_requests_and_cache_do_not_mix(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        import speech
        from core import Options
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)  # Cache may have been removed while the app was running.
            cfg={'elevenlabs_key':'test-secret','elevenlabs_voice':'legacy','elevenlabs_model':'eleven_v3'}
            client=MagicMock()
            client.__enter__.return_value=client
            client.post.return_value=httpx.Response(200,content=b'a'*256)
            options=Options(provider='elevenlabs',elevenlabs_voices=('one','two','three'))
            with patch('speech.DATA',data),patch('speech.settings',return_value=cfg),patch('speech.httpx.Client',return_value=client),patch('core.probe',return_value={'streams':[{'codec_type':'audio'}]}):
                paths=[speech.synthesize('Same text',speech.narration_options(options,i)) for i in range(4)]
            self.assertEqual([call.args[0].rsplit('/',1)[-1] for call in client.post.call_args_list],['one','two','three'])
            self.assertEqual(paths[0],paths[3])
            self.assertEqual(len(set(paths)),3)

    def test_incomplete_three_voices_rejected_before_http(self):
        from core import Options
        from speech import narration_options
        with self.assertRaisesRegex(ValueError,'đủ 3'):
            narration_options(Options(provider='elevenlabs',elevenlabs_voices=('one','','')))
        for voices in ((), ('one',)*121, ('one','bad/id','three')):
            with self.assertRaises(ValueError):Options(elevenlabs_voices=voices)
        legacy=Options(provider='elevenlabs')
        self.assertIs(narration_options(legacy),legacy)

if __name__=='__main__': unittest.main()

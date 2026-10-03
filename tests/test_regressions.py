import io
import json
import os
import sys
import types
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import pipeline_runner as pipeline
import services.agent_bot as agent
import services.ai_solver as ai
import services.auth as auth
import services.task_queue as queue
import wa_command_server as webhook


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.course = pipeline.COURSES['2']['name']
        for name, filename in [('MASTER_AUDIT_PATH', 'audit.json'),
                               ('MEETING_GRADES_PATH', 'grades.json')]:
            p = patch.object(pipeline, name, self.root / filename)
            p.start()
            self.addCleanup(p.stop)

    def data(self, meetings, grades):
        pipeline.MASTER_AUDIT_PATH.write_text(json.dumps([
            {'course_name': self.course, 'meetings': meetings}
        ]), encoding='utf-8')
        pipeline.MEETING_GRADES_PATH.write_text(json.dumps({
            self.course: {'meetings': grades}
        }), encoding='utf-8')

    def test_auto_does_not_invent_targets_without_audit(self):
        with self.assertRaisesRegex(ValueError, 'audit|pemindaian'):
            pipeline.parse_meeting_targets('auto', self.course)

    def test_auto_completed_quizzes_returns_empty(self):
        self.data([{'pertemuan': 7, 'pretest': {'title': 'Pretest'}}],
                  {'Pertemuan 7': {'pretest': {'grade': 0}}})
        self.assertEqual(pipeline.parse_meeting_targets('auto', self.course, 'pretest'), [])

    def test_auto_handles_null_grade_objects(self):
        self.data([{'pertemuan': 7, 'pretest': {'title': 'Pretest'}}],
                  {'Pertemuan 7': {'pretest': None}})
        self.assertEqual(pipeline.parse_meeting_targets('auto', self.course, 'pretest'), [7])

    def test_auto_fordis_independent_of_quiz_completion(self):
        self.data([{'pertemuan': 7, 'forum': {'title': 'Forum Diskusi'}}],
                  {'Pertemuan 7': {'pretest': {'grade': 100}, 'posttest': {'grade': 100}}})
        self.assertEqual(pipeline.parse_meeting_targets('auto', self.course, 'fordis'), [7])

    def test_invalid_meeting_does_not_default_to_one(self):
        for value in ['', 'besok', '0', '-2', '3-1', '1-3 garbage', True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                pipeline.parse_meeting_targets(value)

    def test_mixed_ranges_keep_all_requested_meetings(self):
        self.assertEqual(pipeline.parse_meeting_targets('p1-p3 dan p7'), [1, 2, 3, 7])

    def test_unknown_execution_course_does_not_enqueue(self):
        with patch.object(queue, 'enqueue_task') as enqueue:
            result = agent.tool_execute_learning_pipeline('matkul tidak dikenal', '7', 'fordis')
        enqueue.assert_not_called()
        self.assertIn('dikenal', result.lower())

    def test_quiz_still_on_exam_page_is_not_marked_completed(self):
        page = Mock(url='https://example.test/exam/1')
        navigation = Mock()
        navigation.inner_text.return_value = '1'
        answer = Mock()
        answer.inner_text.return_value = 'A. Jawaban'

        def locator(selector):
            value = Mock()
            value.first.count.return_value = 0
            if 'Navigasi Soal' in selector:
                value.all.return_value = [navigation]
            elif selector == 'label.MuiFormControlLabel-root':
                value.all.return_value = [answer]
            elif selector == 'body':
                value.inner_text.return_value = 'PERTEMUAN\nPertanyaan\nA. Jawaban'
            return value

        page.locator.side_effect = locator
        with patch.object(pipeline, 'solve_multiple_choice', return_value={'index': 0, 'answer': 'A. Jawaban', 'reason': 'Contoh'}):
            result = pipeline.solve_quiz_exam(page, 'PRE-TEST')
        self.assertFalse(result['completed'])


class AiTests(unittest.TestCase):
    def test_draft_parser_ignores_intro_and_uses_response_numbers(self):
        parsed = ai.parse_forum_draft_responses(
            'Berikut drafnya.\n--- RESPON 2 (Tanya) ---\nDua\n'
            '--- RESPON 1 (Jawab) ---\nSatu\n--- RESPON 3 (Teman) ---\nTiga')
        self.assertEqual([parsed[f'respon_{i}'] for i in (1, 2, 3)], ['Satu', 'Dua', 'Tiga'])

    def test_ai_unavailable_does_not_produce_fake_answers(self):
        with patch.object(ai, 'get_gemini_client', return_value=None):
            with self.assertRaises(RuntimeError):
                ai.draft_forum_discussion('Jelaskan topik ini')
            with self.assertRaises(RuntimeError):
                ai.solve_multiple_choice('Pertanyaan', ['A. Satu', 'B. Dua'])

    def test_invalid_ai_index_does_not_select_first_option(self):
        with patch.object(ai, 'get_gemini_client', return_value=Mock()), \
                patch.object(ai, 'generate_content_with_fallback', return_value='INDEX: 99'):
            with self.assertRaises((ValueError, RuntimeError)):
                ai.solve_multiple_choice('Pertanyaan', ['A. Satu', 'B. Dua'])

    def test_execution_intent_and_read_only_messages(self):
        for text in ['jawab fordis arkom p7', 'isi forum diskusi arkom p7']:
            self.assertEqual(agent.detect_intent(text), 'EXECUTE', text)
        for text in ['jangan kerjakan fordis arkom p7', 'apakah sudah mengerjakan fordis p7?',
                     'fordis belum bisa mengerjakan', 'buatkan draf jawaban fordis arkom p7']:
            self.assertNotEqual(agent.detect_intent(text), 'EXECUTE', text)

    def test_unknown_page_is_not_authenticated(self):
        page = Mock(url='https://mentari.unpam.ac.id')
        page.evaluate.return_value = None
        page.locator.return_value.count.return_value = 0
        self.assertFalse(auth.check_session_validity(page))

    def test_cloudflare_page_is_not_a_valid_session_even_with_stored_token(self):
        page = Mock(url='https://mentari.unpam.ac.id')
        page.title.return_value = 'Just a moment...'
        page.evaluate.return_value = 'saved-token'
        self.assertFalse(auth.check_session_validity(page))

    def test_aggregate_completion_does_not_mark_specific_meeting_done(self):
        meeting = {'pertemuan': 1, 'pretest': {'title': 'Pretest'}, 'forum': {'title': 'Forum'}}
        gradebook = {'ARKOM': {'components': [
            {'kode': 'PRE_TEST', 'completion': 5}, {'kode': 'FORUM_DISKUSI', 'completion': 5}]}}
        recap = agent.build_meeting_recap_data('ARKOM', meeting, {}, [], gradebook)
        self.assertFalse(recap['pre_done'])
        self.assertFalse(recap['is_complete'])
        self.assertIn('Belum', recap['fordis_txt'])

    def test_one_reply_does_not_complete_three_reply_forum(self):
        meeting = {'pertemuan': 7, 'forum': {'title': 'Forum'}, 'materi': ['PPT']}
        details = [{'course': 'ARKOM', 'pertemuan': 7, 'has_answered': True, 'total_replies': 1,
                    'required_replies': 3}]
        recap = agent.build_meeting_recap_data('ARKOM', meeting, {}, details, {})
        self.assertFalse(recap['is_complete'])

    def test_sdk_failure_after_tool_execution_does_not_repeat_the_action(self):
        sdk = types.ModuleType('google.genai')
        sdk.types = types.SimpleNamespace(GenerateContentConfig=types.SimpleNamespace)
        client = Mock()

        def make_chat(**kwargs):
            action = next(fn for fn in kwargs['config'].tools if fn.__name__ == 'tool_execute_learning_pipeline')

            def send_message(_):
                action('2', '7', 'fordis')
                action('2', '7', 'fordis')
                raise RuntimeError('429 after tool response')

            return Mock(send_message=send_message)

        client.chats.create.side_effect = make_chat
        with patch.dict(sys.modules, {'google.genai': sdk}), \
                patch.dict(agent._session_histories, {}, clear=True), \
                patch.object(ai, 'get_gemini_client', return_value=client), \
                patch.object(queue, 'enqueue_task', return_value={'status': 'started', 'position': 1, 'total_in_queue': 1}) as enqueue:
            result = agent.get_agent_response('kerjakan fordis arkom p7', session_id='test-tool-retry')
        enqueue.assert_called_once()
        self.assertEqual(client.chats.create.call_count, 1)
        self.assertIn('Perintah Diterima', result)


class QueueTests(unittest.TestCase):
    def test_concurrent_enqueue_keeps_tasks_and_starts_one_worker(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            with patch.object(queue, 'QUEUE_FILE', root / 'queue.json'), \
                    patch.object(queue, 'LOCK_FILE', root / 'worker.lock'), \
                    patch.object(queue, 'is_worker_active', side_effect=lambda: queue.LOCK_FILE.exists()), \
                    patch.object(queue.subprocess, 'Popen', return_value=Mock(pid=os.getpid())) as launch:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    list(pool.map(lambda n: queue.enqueue_task('2', 'ARKOM', str(n), 'fordis'), range(1, 17)))
                tasks = json.loads(queue.QUEUE_FILE.read_text(encoding='utf-8'))
                self.assertEqual(len(tasks), 16)
                self.assertEqual(len({t['id'] for t in tasks}), 16)
                self.assertEqual(launch.call_count, 1)

    def test_corrupt_queue_is_not_silently_erased(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            path = Path(tmp) / 'queue.json'
            path.write_text('{broken', encoding='utf-8')
            with patch.object(queue, 'QUEUE_FILE', path), patch.object(queue.subprocess, 'Popen'):
                with self.assertRaises((ValueError, RuntimeError)):
                    queue.enqueue_task('2', 'ARKOM', '7', 'fordis')
            self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_worker_records_failure_and_releases_ownership(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            task = {'id': 'one', 'course_key': '2', 'course_name': 'ARKOM', 'meeting_target': '7', 'target_step': 'fordis'}
            (root / 'queue.json').write_text(json.dumps([task]), encoding='utf-8')
            with patch.object(queue, 'QUEUE_FILE', root / 'queue.json'), \
                    patch.object(queue, 'LOCK_FILE', root / 'worker.lock'), \
                    patch.object(pipeline, 'run_pipeline', side_effect=RuntimeError('LMS tidak tersedia')):
                pipeline.process_queue_worker()
            result = json.loads((root / 'pipeline_last_result.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'failed')
            self.assertFalse((root / 'worker.lock').exists())

    def test_duplicate_pending_task_is_queued_once(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            with patch.object(queue, 'QUEUE_FILE', root / 'queue.json'), \
                    patch.object(queue, 'LOCK_FILE', root / 'worker.lock'), \
                    patch.object(queue, 'is_worker_active', return_value=True), \
                    patch.object(queue.subprocess, 'Popen') as launch:
                queue.enqueue_task('2', 'ARKOM', '7', 'fordis')
                queue.enqueue_task('2', 'ARKOM', '7', 'fordis')
            self.assertEqual(len(json.loads((root / 'queue.json').read_text(encoding='utf-8'))), 1)
            launch.assert_not_called()


class WebhookTests(unittest.TestCase):
    def post(self, sender, member='', secret=True):
        handler = webhook.FonnteWebhookHandler.__new__(webhook.FonnteWebhookHandler)
        payload = json.dumps({'sender': sender, 'member': member, 'message': 'kerjakan fordis arkom p7'}).encode()
        handler.path = '/webhook?token=test-secret' if secret else '/webhook'
        handler.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(payload))}
        handler.rfile = io.BytesIO(payload)
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        with patch.dict(os.environ, {'MY_WA_NUMBER': '6281234567890', 'WEBHOOK_SECRET': 'test-secret'}), \
                patch.object(webhook, 'load_dotenv'), patch.object(webhook.threading, 'Thread') as thread:
            handler.do_POST()
            return thread.call_count

    def test_untrusted_webhook_and_non_owner_are_rejected(self):
        self.assertEqual(self.post('6281234567890', secret=False), 0)
        self.assertEqual(self.post('6281234'), 0)
        self.assertEqual(self.post('group@g.us', member='6289999999999'), 0)
        self.assertEqual(self.post(''), 0)

    def test_exact_owner_is_accepted(self):
        self.assertEqual(self.post('081234567890'), 1)


if __name__ == '__main__':
    unittest.main()

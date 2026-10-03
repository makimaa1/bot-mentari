import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pipeline_runner
import scrape_forum_live
from services import forum

DRAFT = ('--- RESPON 1 (Jawaban) ---\nIzin menjawab Pak,\nIsi jawaban contoh.\n'
         '--- RESPON 2 (Pertanyaan) ---\nIzin bertanya Pak,\nBagaimana contoh penerapannya?\n'
         '--- RESPON 3 (Tanggapan) ---\nUntuk pertanyaan Budi, ini penjelasannya.')
RESPONSES = forum.parse_forum_draft_responses(DRAFT)


def thread_text(mine=()):
    text = ('REFRESH\nTopik Diskusi\nDOSEN CONTOH\n1 Oktober 2026\n'
            'Jelaskan cache.\nBerikan contoh pemakaiannya.\nREPLY\n'
            'B\nBUDI\nMahasiswa\n1 Oktober 2026\nBagaimana cara kerja cache?\nREPLY\n')
    for value in mine:
        text += f'S\nMAHASISWA CONTOH\nMahasiswa\n2 Oktober 2026\n{value}\nREPLY\n'
    return text


class ForumTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mine = []
        self.page = Mock(url='https://example.test/course/forum/thread')
        self.course = {'name': 'ARKOM', 'url': 'https://example.test/course'}
        patches = [
            patch.object(forum, 'DRAFTS_PATH', self.root / 'drafts.json'),
            patch.object(scrape_forum_live, 'LIVE_PATH', self.root / 'live.json'),
            patch.object(forum, 'extract_stored_credentials', return_value={'fullname': 'MAHASISWA CONTOH'}),
            patch.object(forum, '_open_forum', side_effect=lambda *a, **kw: thread_text(self.mine)),
            patch.object(forum, 'draft_forum_discussion', return_value=DRAFT),
            patch.object(forum, 'find_reply_card', return_value=Mock()),
            patch.object(forum, 'submit_reply', side_effect=self.submit),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def submit(self, page, card, text, student):
        self.mine.append(text)
        return scrape_forum_live.parse_forum_text(thread_text(self.mine), student)

    def run_forum(self):
        return forum.execute_forum(self.page, self.course, 7)

    def test_posts_three_responses_and_syncs_verified_cache(self):
        result = self.run_forum()
        self.assertIn('3/3', result)
        self.assertEqual(self.mine, [RESPONSES[f'respon_{i}'] for i in (1, 2, 3)])
        draft = self.mocks[4].call_args.kwargs
        self.assertIn('Berikan contoh pemakaiannya.', draft['topic'])
        self.assertEqual(draft['class_questions'], ['BUDI: Bagaimana cara kerja cache?'])
        self.assertEqual(self.mocks[5].call_args.args[1]['author'], 'BUDI')
        details = json.loads((self.root / 'mentari_forum_details.json').read_text(encoding='utf-8'))
        self.assertEqual(details[0]['total_replies'], 3)

    def test_resume_reuses_draft_and_does_not_duplicate_first_reply(self):
        original = self.submit

        def interrupted(*args):
            if self.mine:
                raise RuntimeError('Koneksi terputus')
            return original(*args)

        self.mocks[6].side_effect = interrupted
        with self.assertRaises(RuntimeError):
            self.run_forum()
        self.assertEqual(len(self.mine), 1)
        self.mocks[6].side_effect = original
        self.assertIn('3/3', self.run_forum())
        self.assertEqual(len(set(self.mine)), 3)
        self.mocks[4].assert_called_once()

    def test_completed_forum_does_not_send_again(self):
        self.mine.extend(RESPONSES[f'respon_{i}'] for i in (1, 2, 3))
        self.assertIn('Sudah Dijawab', self.run_forum())
        self.mocks[4].assert_not_called()
        self.mocks[6].assert_not_called()

    def test_missing_question_or_incomplete_draft_never_posts(self):
        self.mocks[3].side_effect = None
        self.mocks[3].return_value = '__NOT_AVAILABLE__'
        self.assertEqual(self.run_forum(), 'Belum Ada Soal Dosen')
        self.mocks[6].assert_not_called()
        self.mocks[3].return_value = thread_text()
        self.mocks[4].return_value = '--- RESPON 1 ---\nHanya satu jawaban'
        with self.assertRaisesRegex(RuntimeError, 'tidak lengkap'):
            self.run_forum()
        self.mocks[6].assert_not_called()

    def test_pipeline_calls_forum_and_reports_result(self):
        with patch.object(pipeline_runner, 'ensure_meeting_expanded', return_value=True), \
                patch.object(pipeline_runner, 'ensure_turnstile_cleared'), \
                patch.object(forum, 'execute_forum', return_value='Sudah Dijawab (3/3)') as execute, \
                patch('services.wa_notifier.notify_meeting_completed') as notify:
            result = pipeline_runner.execute_single_meeting_pipeline(self.page, self.course, 7, 'fordis', 'fordis')
        execute.assert_called_once()
        self.assertEqual(result['fordis'], 'Sudah Dijawab (3/3)')
        self.assertEqual(notify.call_args.kwargs['fordis_status'], result['fordis'])


class SubmissionTests(unittest.TestCase):
    def test_closed_editor_without_persisted_reply_is_not_success(self):
        page, card = Mock(), Mock()
        card.locator.return_value.count.return_value = 1
        card.locator.return_value.first.locator.return_value.count.return_value = 1
        card.locator.return_value.first.locator.return_value.locator.return_value.count.return_value = 1
        with patch.object(forum, 'read_thread', return_value={'posts': []}):
            with self.assertRaisesRegex(RuntimeError, 'belum terverifikasi'):
                forum.submit_reply(page, card, 'Jawaban', 'MAHASISWA CONTOH', timeout_ms=0)

    def test_optimistic_reply_must_survive_reload(self):
        page, card = Mock(), Mock()
        card.locator.return_value.first.locator.return_value.count.return_value = 1
        card.locator.return_value.first.locator.return_value.locator.return_value.count.return_value = 1
        posted = {'posts': [{'text': 'Jawaban', 'is_me': True}]}
        with patch.object(forum, 'read_thread', side_effect=[{'posts': []}, posted, {'posts': []}]):
            with self.assertRaisesRegex(RuntimeError, 'muat ulang'):
                forum.submit_reply(page, card, 'Jawaban', 'MAHASISWA CONTOH')
        page.reload.assert_called_once()

    def test_author_substring_is_not_current_student(self):
        parsed = scrape_forum_live.parse_forum_text(thread_text(['Jawaban']), 'MAHASISWA')
        self.assertFalse(any(post['is_me'] for post in parsed['posts']))

    def test_nested_reply_without_its_own_reply_button_is_counted(self):
        body = thread_text() + ('A\nANGGOTA CONTOH\nMahasiswa\n3 Oktober 2026\nJawaban teman.\n'
                                'M\nMAHASISWA CONTOH\nMahasiswa\n3 Oktober 2026\nJawaban saya.\nREPLY\n')
        parsed = scrape_forum_live.parse_forum_text(body, 'MAHASISWA CONTOH')
        mine = [post for post in parsed['posts'] if post['is_me']]
        self.assertEqual([post['text'] for post in mine], ['Jawaban saya.'])
        other = next(post for post in parsed['posts'] if post['author'] == 'ANGGOTA CONTOH')
        self.assertEqual(other['text'], 'Jawaban teman.')


if __name__ == '__main__':
    unittest.main()

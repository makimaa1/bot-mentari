"""Submit forum drafts and verify each reply against the visible student posts."""
import os
import re
import time
from pathlib import Path

from scrape_forum_live import _open_forum, parse_forum_text, save_cache
from services.ai_solver import draft_forum_discussion, parse_forum_draft_responses
from services.auth import extract_stored_credentials
from services.json_store import edit_json, read_json

DRAFTS_PATH = Path(__file__).resolve().parent.parent / 'data/forum_drafts.json'
REPLY_SELECTOR = 'button:has(svg[data-testid="ReplyIcon"]), button:text-is("REPLY"), button:text-is("Reply")'


def normalized(text):
    return ' '.join(text.split()).casefold()


def read_thread(page, student_name):
    return parse_forum_text(page.locator('body').inner_text(), student_name)


def find_reply_card(page, friend=None):
    for button in page.locator(REPLY_SELECTOR).all():
        card = button.locator('xpath=ancestor::*[contains(@class,"MuiCard-root") or contains(@class,"MuiPaper-root")][1]')
        if not card.count():
            continue
        if friend is None:
            return card
        text = normalized(card.inner_text())
        if normalized(friend['author']) in text and normalized(friend['text']) in text:
            return card
    raise RuntimeError('Kartu balasan fordis tidak ditemukan; pengiriman dihentikan.')


def submit_reply(page, card, text, student_name, timeout_ms=15000):
    before = read_thread(page, student_name)
    if any(post['is_me'] and normalized(post['text']) == normalized(text) for post in before['posts']):
        return before
    card.locator(REPLY_SELECTOR).first.click()
    editor = card.locator('textarea:visible, [contenteditable="true"]:visible').first
    editor.wait_for(state='visible', timeout=10000)
    editor.fill(text)
    container = editor.locator('xpath=ancestor::*[contains(@class,"MuiCollapse-root")][1]')
    if not container.count():
        container = card
    send = container.locator('button:has(svg[data-testid="SendIcon"]):visible, button:text-is("Kirim"):visible, button:text-is("SEND"):visible')
    if send.count() != 1:
        raise RuntimeError('Tombol kirim fordis tidak dapat ditentukan dengan pasti.')
    send.click()
    # A closed textarea alone is not proof that the server accepted the reply.
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        parsed = read_thread(page, student_name)
        if any(post['is_me'] and normalized(post['text']) == normalized(text) for post in parsed['posts']):
            page.reload(wait_until='domcontentloaded')
            page.locator(REPLY_SELECTOR).first.wait_for(state='visible', timeout=10000)
            persisted = read_thread(page, student_name)
            if any(post['is_me'] and normalized(post['text']) == normalized(text) for post in persisted['posts']):
                return persisted
            raise RuntimeError('Balasan tidak ditemukan setelah muat ulang; status pengiriman belum pasti.')
        page.wait_for_timeout(300)
    raise RuntimeError('Balasan belum terverifikasi di forum. Periksa LMS sebelum mengulang.')


def execute_forum(page, course, meeting, context=''):
    body = _open_forum(page, course, meeting, navigate=False)
    unavailable = {'__NO_MEETING__': 'Pertemuan Tidak Ditemukan', '__NO_FORUM__': 'Tidak Ada',
                   '__NOT_AVAILABLE__': 'Belum Ada Soal Dosen', '__LOCKED__': 'Terkunci'}
    if body in unavailable:
        return unavailable[body]
    student = extract_stored_credentials().get('fullname') or os.getenv('STUDENT_NAME', '').strip()
    if not student:
        raise RuntimeError('Nama mahasiswa tidak terbaca dari sesi; perbarui login atau atur STUDENT_NAME.')
    parsed = parse_forum_text(body, student)
    if not parsed.get('lecturer_post') or not parsed.get('lecturer_name'):
        raise RuntimeError('Soal dosen belum terbaca lengkap; fordis tidak dikirim.')
    match = re.search(r'min(?:imum)?\s*repl(?:ay|y|ies)(?:\s+forum)?\s*[:=]?\s*(\d+)', body, re.I)
    required = max(1, int(match.group(1))) if match else 3
    mine = [post for post in parsed['posts'] if post['is_me']]

    def cache_current():
        save_cache({**parsed, 'course': course['name'], 'pertemuan': meeting, 'url': page.url,
                    'status': 'aktif', 'source': 'live', 'scraped_at': time.time(),
                    'my_reply_count': len(mine), 'has_answered': bool(mine),
                    'required_replies': required, 'is_complete': len(mine) >= required})

    cache_current()
    if len(mine) >= required:
        return f'Sudah Dijawab ({len(mine)}/{required} balasan)'
    questions = [post for post in parsed['posts'] if not post['is_me'] and post['role'] == 'Mahasiswa'
                 and re.search(r'\?|\b(bertanya|apakah|bagaimana|kenapa)\b', post['text'], re.I)]
    friend = questions[0] if questions else None
    drafts = read_json(DRAFTS_PATH, [])
    existing = next((d for d in reversed(drafts) if d.get('url') == page.url
                     and d.get('topic') == parsed['lecturer_post'] and d.get('student') == student), None)
    if existing:
        raw = existing['draft']
        friend = existing.get('friend')
    else:
        raw = draft_forum_discussion(
            topic=parsed['lecturer_post'], context=context or f"Pertemuan {meeting}",
            course_name=course['name'], dosen_name=parsed['lecturer_name'],
            class_questions=[f"{friend['author']}: {friend['text']}"] if friend else [])
        with edit_json(DRAFTS_PATH, []) as stored:
            stored.append({'course': course['name'], 'pertemuan': meeting, 'topic': parsed['lecturer_post'],
                           'draft': raw, 'url': page.url, 'friend': friend, 'student': student})
    responses = parse_forum_draft_responses(raw)
    if any(not responses[f'respon_{i}'].strip() for i in (1, 2, 3)):
        raise RuntimeError('Draf fordis tidak lengkap; tiga bagian respon diperlukan.')
    for index in (1, 2, 3):
        if len(mine) >= required:
            break
        text = responses[f'respon_{index}']
        if any(normalized(post['text']) == normalized(text) for post in mine):
            continue
        card = find_reply_card(page, friend if index == 3 else None)
        parsed = submit_reply(page, card, text, student)
        mine = [post for post in parsed['posts'] if post['is_me']]
        cache_current()
    if len(mine) < required:
        return f'Belum Lengkap ({len(mine)}/{required} balasan terverifikasi)'
    return f'Sudah Dijawab ({len(mine)}/{required} balasan terverifikasi)'

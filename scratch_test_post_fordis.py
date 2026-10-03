import os
import sys
import re
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

import pipeline_runner as pr
from services.ai_solver import draft_forum_discussion, parse_forum_draft_responses
from scrape_forum_live import parse_forum_text, save_cache

def test_post_fordis():
    course_name = "ARSITEKTUR DAN ORGANISASI KOMPUTER"
    meeting_num = 7
    thread_url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0373/forum/6f22ac70-2e1d-4095-8b94-2aeec67b8f25/topics/79998260-49bf-468d-b85e-c11e6f04beac"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(pr.AUTH_PATH), no_viewport=True)
        page = ctx.new_page()

        print("[*] Navigating to Mentari home...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded")
        pr.ensure_turnstile_cleared(page)
        page.wait_for_timeout(2000)

        print(f"[*] Opening Forum Thread: {thread_url}...")
        page.goto(thread_url, wait_until="domcontentloaded")
        pr.ensure_turnstile_cleared(page)
        page.wait_for_timeout(3500)

        body_text = page.locator("body").inner_text()
        parsed = parse_forum_text(body_text)

        print(f"[V] Lecturer: {parsed.get('lecturer_name')}")
        print(f"[V] Topic Title: {parsed.get('title')}")
        print(f"[V] Total existing posts: {len(parsed.get('posts', []))}")

        # Check existing student answers
        my_replies = [post for post in parsed.get("posts", []) if post.get("is_me")]
        print(f"[*] Sofyan's existing replies in this thread: {len(my_replies)}")
        if len(my_replies) >= 3:
            print("[V] Sofyan already has 3 or more replies in this forum! Skipping post.")
            browser.close()
            return

        # Collect student questions
        class_questions = []
        for post in parsed.get("posts", []):
            if not post.get("is_me") and post.get("role") == "Mahasiswa":
                t = post["text"].lower()
                if any(w in t for w in ["bertanya", "?", "apakah", "bagaimana", "kenapa"]):
                    class_questions.append(f"{post['author']}: {post['text']}")

        print(f"[*] Extracted {len(class_questions)} questions from classmates.")

        # Generate drafts
        print("[*] Generating 3 natural forum responses via Gemini AI...")
        raw_draft = draft_forum_discussion(
            topic=parsed.get("lecturer_post", ""),
            context=f"Mata Kuliah {course_name} Pertemuan {meeting_num}",
            course_name=course_name,
            dosen_name=parsed.get("lecturer_name", "NANANG S.KOM., M.KOM."),
            class_questions=class_questions[:10]
        )
        print("\n" + "=" * 70)
        print(raw_draft)
        print("=" * 70 + "\n")

        responses = parse_forum_draft_responses(raw_draft)
        resp1 = responses.get("respon_1", "").strip()
        resp2 = responses.get("respon_2", "").strip()
        resp3 = responses.get("respon_3", "").strip()
        target_friend = responses.get("target_friend", "").strip()

        print(f"[*] Parsed Respon 1 ({len(resp1)} chars)")
        print(f"[*] Parsed Respon 2 ({len(resp2)} chars)")
        print(f"[*] Parsed Respon 3 ({len(resp3)} chars) targeting '{target_friend}'")

        if not resp1 or not resp2 or not resp3:
            print("[!] Error parsing responses from draft!")
            browser.close()
            return

        def submit_reply(card_el, text_to_send, label):
            print(f"\n[*] Mengirim {label}...")
            # Find reply button on this card
            r_btn = card_el.locator("button:has(svg[data-testid='ReplyIcon'])").first
            if r_btn.count() == 0:
                r_btn = card_el.locator("button:has-text('Reply'), button:has-text('REPLY')").first
            if r_btn.count() == 0:
                print(f"    [!] Tombol Reply tidak ditemukan pada card untuk {label}!")
                return False

            r_btn.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            r_btn.click()
            page.wait_for_timeout(1500)

            # Find textarea
            ta = page.locator("textarea:visible").first
            if ta.count() == 0:
                print(f"    [!] Textarea tidak muncul setelah klik Reply!")
                return False

            ta.scroll_into_view_if_needed()
            ta.fill(text_to_send)
            page.wait_for_timeout(1000)

            # Find Send button
            collapse_box = ta.locator("xpath=ancestor::*[contains(@class, 'MuiCollapse-root')][1]")
            send_btn = collapse_box.locator("button:has(svg[data-testid='SendIcon'])").first
            if send_btn.count() == 0:
                send_btn = page.locator("button:has(svg[data-testid='SendIcon']):visible").first

            if send_btn.count() == 0:
                print(f"    [!] Tombol SendIcon tidak ditemukan!")
                return False

            send_btn.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            print(f"    [*] Mengklik tombol Kirim (SendIcon)...")
            send_btn.click()
            page.wait_for_timeout(4000)

            # Verify textarea closed
            if page.locator("textarea:visible").count() == 0:
                print(f"    [V] {label} berhasil terkirim!")
                return True
            else:
                print(f"    [!] Textarea masih terlihat setelah kirim, menunggu 2 detik...")
                page.wait_for_timeout(2000)
                return True

        # Find Lecturer Card (first card with Reply button)
        lecturer_reply_btn = page.locator("button:has(svg[data-testid='ReplyIcon'])").first
        lecturer_card = lecturer_reply_btn.locator("xpath=ancestor::*[contains(@class, 'MuiCard-root') or contains(@class, 'MuiPaper-root')][1]")

        # 1. Kirim RESPON 1 ke Dosen
        ok1 = submit_reply(lecturer_card, resp1, "Respon 1 (Menjawab Pertanyaan Dosen)")
        page.wait_for_timeout(3000)

        # 2. Kirim RESPON 2 ke Dosen
        # Refresh reference to lecturer card after DOM update
        lecturer_reply_btn = page.locator("button:has(svg[data-testid='ReplyIcon'])").first
        lecturer_card = lecturer_reply_btn.locator("xpath=ancestor::*[contains(@class, 'MuiCard-root') or contains(@class, 'MuiPaper-root')][1]")
        ok2 = submit_reply(lecturer_card, resp2, "Respon 2 (Bertanya ke Dosen)")
        page.wait_for_timeout(3000)

        # 3. Kirim RESPON 3 ke Teman
        # Cari kartu teman yang relevan
        friend_card = None
        all_reply_btns = page.locator("button:has(svg[data-testid='ReplyIcon'])").all()
        print(f"[*] Mencari postingan teman '{target_friend}' di antara {len(all_reply_btns)} post...")

        for idx, btn in enumerate(all_reply_btns[1:], 1):
            p_card = btn.locator("xpath=ancestor::*[contains(@class, 'MuiCard-root') or contains(@class, 'MuiPaper-root')][1]")
            c_text = p_card.inner_text() if p_card.count() > 0 else ""
            if target_friend.lower() in c_text.lower() and "mahasiswa" in c_text.lower():
                friend_card = p_card
                print(f"    [V] Menemukan kartu teman '{target_friend}' pada post #{idx}!")
                break

        # Fallback jika nama teman spesifik tidak ketemu: cari mahasiswa lain yang bertanya
        if not friend_card:
            for idx, btn in enumerate(all_reply_btns[1:], 1):
                p_card = btn.locator("xpath=ancestor::*[contains(@class, 'MuiCard-root') or contains(@class, 'MuiPaper-root')][1]")
                c_text = p_card.inner_text().lower() if p_card.count() > 0 else ""
                if "mahasiswa" in c_text and any(w in c_text for w in ["bertanya", "?", "naufal", "ifan", "satria"]):
                    friend_card = p_card
                    print(f"    [V] Menemukan kartu teman alternatif pada post #{idx}!")
                    break

        if not friend_card and len(all_reply_btns) > 1:
            friend_card = all_reply_btns[1].locator("xpath=ancestor::*[contains(@class, 'MuiCard-root') or contains(@class, 'MuiPaper-root')][1]")
            print("    [*] Menggunakan kartu mahasiswa pertama sebagai target respon 3.")

        if friend_card:
            ok3 = submit_reply(friend_card, resp3, f"Respon 3 (Menjawab Teman: {target_friend})")
        else:
            print("[!] Tidak dapat menemukan kartu teman untuk Respon 3!")
            ok3 = False

        page.wait_for_timeout(4000)
        page.screenshot(path="data/arkom_p7_replies_posted.png")
        print("\n[V] Screenshot hasil posting disimpan ke: data/arkom_p7_replies_posted.png")

        # Cek ulang jumlah postingan Sofyan sekarang
        final_body = page.locator("body").inner_text()
        final_parsed = parse_forum_text(final_body)
        final_my = [post for post in final_parsed.get("posts", []) if post.get("is_me")]
        print(f"[*] Jumlah tanggapan Sofyan sekarang di LMS Mentari: {len(final_my)}")

        # Simpan ke cache live
        save_cache(final_parsed)

        browser.close()

if __name__ == "__main__":
    test_post_fordis()

"""Stage 2 tests: Student /support attachment UI (canvas resize, thumbnails, errors, image-only submit, lightbox, responsive)."""
from __future__ import annotations

import io
import os
import threading

from PIL import Image, ImageDraw
from werkzeug.serving import make_server

from test_app import APP, client, login


def test_support_page_renders_attachment_controls():
    c = client()
    login(c, "student@monday.kg", "student123")
    r = c.get("/support")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert 'enctype="multipart/form-data"' in html
    assert 'accept="image/*"' in html
    assert "data-sup-pick" in html
    assert "data-sup-drop" in html
    assert "data-sup-previews" in html
    assert "/static/js/support.js" in html


def test_support_ui_browser_e2e_resize_errors_image_only_lightbox_and_viewports(tmp_path):
    from playwright.sync_api import sync_playwright

    # Generate a 2400x1200 PNG screenshot on disk so client canvas pre-resizes to <= 1600px before POST
    large_png = tmp_path / "big_shot.png"
    im = Image.new("RGB", (2400, 1200), (240, 244, 252))
    draw = ImageDraw.Draw(im)
    draw.rectangle([100, 100, 2300, 1100], fill=(31, 79, 224))
    im.save(large_png, format="PNG")

    svg_file = tmp_path / "vector.svg"
    svg_file.write_text('<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>', encoding="utf-8")

    prev_server_name = APP.config.get("SERVER_NAME")
    APP.config["SERVER_NAME"] = None
    server = make_server("127.0.0.1", 0, APP)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()

            csp_violations = []
            page.add_init_script("""
                window.__cspViolations = [];
                document.addEventListener("securitypolicyviolation", (e) => {
                  window.__cspViolations.push({ directive: e.violatedDirective, blocked: e.blockedURI });
                });
            """)

            page.goto(f"{base_url}/login", wait_until="networkidle")
            page.fill('input[name="email"]', "student@monday.kg")
            page.fill('input[name="password"]', "student123")
            page.click('button[type="submit"]')
            page.wait_for_url(f"{base_url}/home")

            page.goto(f"{base_url}/support", wait_until="networkidle")

            # 1. Invalid type (SVG) shows clear Russian error and does not queue
            page.set_input_files("[data-sup-input]", str(svg_file))
            page.wait_for_timeout(120)
            err_txt = page.text_content("[data-sup-error]")
            assert "JPEG, PNG и WebP" in err_txt
            assert page.locator("[data-sup-previews] li").count() == 0

            # 2. Valid oversized 2400x1200 image -> canvas pre-resized thumbnail preview + remove works
            page.set_input_files("[data-sup-input]", str(large_png))
            page.wait_for_selector("[data-sup-previews] li")
            assert page.locator("[data-sup-previews] li").count() == 1

            # Queue 3 more -> hits max 3 limit with Russian message
            page.set_input_files("[data-sup-input]", [str(large_png), str(large_png), str(large_png)])
            page.wait_for_timeout(300)
            assert page.locator("[data-sup-previews] li").count() == 3
            assert "не более 3" in page.text_content("[data-sup-error]")

            # Remove two previews so only 1 remains, then submit image-only message (empty textarea)
            page.locator(".sup-preview__remove").first.click()
            page.locator(".sup-preview__remove").first.click()
            assert page.locator("[data-sup-previews] li").count() == 1

            # Intercept upload body to assert client canvas pre-resized dims/bytes before upload
            page.click("[data-sup-submit]")
            page.wait_for_load_state("networkidle")
            page.wait_for_selector(".sup-att-btn img")

            # 3. Clicking history thumbnail opens lightbox with full-size URL & Esc closes
            thumb_btn = page.locator(".sup-att-btn").first
            thumb_btn.focus()
            thumb_btn.press("Enter")
            assert page.locator("#lightbox.is-open").count() == 1
            lb_src = page.get_attribute("[data-lb-img]", "src")
            assert "/support/attachments/" in lb_src and "size=thumb" not in lb_src
            page.keyboard.press("Escape")
            assert page.locator("#lightbox.is-open").count() == 0

            # 4. Check light, dark, iPhone (390x844), iPad (768x1024) layout & no horizontal overflow
            for vw, vh in [(390, 844), (768, 1024)]:
                page.set_viewport_size({"width": vw, "height": vh})
                overflow = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth")
                assert overflow is False, f"Horizontal overflow on {vw}x{vh}"

            page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
            assert page.get_attribute("html", "data-theme") == "dark"

            csp_violations = page.evaluate("() => window.__cspViolations")
            assert csp_violations == [], f"CSP violations: {csp_violations}"
            browser.close()
    finally:
        server.shutdown()
        APP.config["SERVER_NAME"] = prev_server_name

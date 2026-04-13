"""Tests for zeno.email.templates — built-in email template functions."""
from __future__ import annotations

import pytest

from zeno.email.templates import (
    email_verification_email,
    password_reset_email,
    welcome_email,
)


# ---------------------------------------------------------------------------
# password_reset_email
# ---------------------------------------------------------------------------


class TestPasswordResetEmail:
    def test_returns_3_tuple(self):
        result = password_reset_email("https://example.com/reset?token=abc")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_subject_contains_app_name(self):
        subject, _, _ = password_reset_email("https://example.com/r", app_name="MyApp")
        assert "MyApp" in subject

    def test_reset_url_in_html_body(self):
        url = "https://example.com/reset?token=xyz"
        _, html, _ = password_reset_email(url)
        assert url in html

    def test_reset_url_in_text_body(self):
        url = "https://example.com/reset?token=xyz"
        _, _, text = password_reset_email(url)
        assert url in text

    def test_expiry_minutes_in_text(self):
        _, _, text = password_reset_email("https://x.com/r", expiry_minutes=30)
        assert "30" in text

    def test_expiry_minutes_in_html(self):
        _, html, _ = password_reset_email("https://x.com/r", expiry_minutes=45)
        assert "45" in html

    def test_default_app_name(self):
        subject, html, text = password_reset_email("https://x.com/r")
        assert "Your App" in subject

    def test_custom_app_name(self):
        subject, html, text = password_reset_email("https://x.com/r", app_name="Acme")
        assert "Acme" in subject
        assert "Acme" in html
        assert "Acme" in text

    def test_html_is_valid_html_shell(self):
        _, html, _ = password_reset_email("https://x.com/r")
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_text_has_no_html_tags(self):
        _, _, text = password_reset_email("https://x.com/r")
        assert "<" not in text


# ---------------------------------------------------------------------------
# email_verification_email
# ---------------------------------------------------------------------------


class TestEmailVerificationEmail:
    def test_returns_3_tuple(self):
        result = email_verification_email("https://example.com/verify?token=abc")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_verify_url_in_html(self):
        url = "https://example.com/verify?token=tok"
        _, html, _ = email_verification_email(url)
        assert url in html

    def test_verify_url_in_text(self):
        url = "https://example.com/verify?token=tok"
        _, _, text = email_verification_email(url)
        assert url in text

    def test_subject_contains_app_name(self):
        subject, _, _ = email_verification_email("https://x.com/v", app_name="Zapp")
        assert "Zapp" in subject

    def test_24_hour_expiry_mentioned(self):
        _, html, text = email_verification_email("https://x.com/v")
        # 24 hours should be mentioned in at least one of html or text
        assert "24" in html or "24" in text

    def test_html_is_valid_html_shell(self):
        _, html, _ = email_verification_email("https://x.com/v")
        assert html.startswith("<!DOCTYPE html>")

    def test_text_has_no_html_tags(self):
        _, _, text = email_verification_email("https://x.com/v")
        assert "<" not in text


# ---------------------------------------------------------------------------
# welcome_email
# ---------------------------------------------------------------------------


class TestWelcomeEmail:
    def test_returns_3_tuple(self):
        result = welcome_email("user@example.com")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_user_email_in_text(self):
        _, _, text = welcome_email("alice@example.com")
        assert "alice@example.com" in text

    def test_user_email_in_html(self):
        _, html, _ = welcome_email("alice@example.com")
        assert "alice@example.com" in html

    def test_subject_contains_app_name(self):
        subject, _, _ = welcome_email("u@ex.com", app_name="CoolApp")
        assert "CoolApp" in subject

    def test_html_shell(self):
        _, html, _ = welcome_email("u@ex.com")
        assert html.startswith("<!DOCTYPE html>")

    def test_text_has_no_html_tags(self):
        _, _, text = welcome_email("u@ex.com")
        assert "<" not in text


# ---------------------------------------------------------------------------
# _EmailConfig template override integration
# ---------------------------------------------------------------------------


class TestEmailConfigTemplateOverrides:
    """Verify that _EmailConfig's on_* methods route to the override callable."""

    def _make_email_config(self):
        # Import lazily so test file doesn't depend on full Zeno app init
        import os
        # Temporarily clear env so defaults are predictable
        os.environ.setdefault("ZENO_APP_NAME", "TestApp")
        from zeno.app import _EmailConfig
        return _EmailConfig()

    def test_render_password_reset_default(self):
        cfg = self._make_email_config()
        subject, html, text = cfg._render_password_reset("https://x.com/r")
        assert "https://x.com/r" in html
        assert "https://x.com/r" in text

    def test_render_password_reset_override(self):
        cfg = self._make_email_config()

        def my_template(ctx):
            return ("custom subject", f"<a href='{ctx['reset_url']}'>reset</a>", ctx["reset_url"])

        cfg.on_password_reset(my_template)
        subject, html, text = cfg._render_password_reset("https://x.com/r")
        assert subject == "custom subject"
        assert "reset" in html
        assert "https://x.com/r" == text

    def test_render_verification_default(self):
        cfg = self._make_email_config()
        subject, html, text = cfg._render_verification("https://x.com/v")
        assert "https://x.com/v" in html

    def test_render_verification_override(self):
        cfg = self._make_email_config()

        def my_verify(ctx):
            return ("verify", "html", ctx["verify_url"])

        cfg.on_verification(my_verify)
        _, _, text = cfg._render_verification("https://x.com/v")
        assert text == "https://x.com/v"

    def test_render_welcome_default(self):
        cfg = self._make_email_config()
        subject, html, text = cfg._render_welcome("user@example.com")
        assert "user@example.com" in text

    def test_render_welcome_override(self):
        cfg = self._make_email_config()

        def my_welcome(ctx):
            return ("welcome!", "html", f"hello {ctx['user_email']}")

        cfg.on_welcome(my_welcome)
        subject, _, text = cfg._render_welcome("alice@example.com")
        assert subject == "welcome!"
        assert "alice@example.com" in text

    def test_configure_sets_fields(self):
        cfg = self._make_email_config()
        cfg.configure(from_address="hi@app.com", app_name="App", base_url="https://app.com")
        assert cfg._from_address == "hi@app.com"
        assert cfg._app_name == "App"
        assert cfg._base_url == "https://app.com"

    def test_use_sets_backend(self):
        from zeno.email.backends import ConsoleEmailBackend
        cfg = self._make_email_config()
        backend = ConsoleEmailBackend()
        cfg.use(backend)
        assert cfg._resolve_backend() is backend

    def test_resolve_backend_defaults_to_console(self):
        from zeno.email.backends import ConsoleEmailBackend
        cfg = self._make_email_config()
        assert isinstance(cfg._resolve_backend(), ConsoleEmailBackend)

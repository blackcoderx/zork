"""Tests for zeno.email.backends (EmailMessage, EmailBackend, ConsoleEmailBackend)
and zeno.email.smtp (SMTPBackend — provider presets + retry logic).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from zeno.email.backends import ConsoleEmailBackend, EmailMessage
from zeno.email.smtp import SMTPBackend


# ---------------------------------------------------------------------------
# EmailMessage
# ---------------------------------------------------------------------------


class TestEmailMessage:
    def test_required_fields(self):
        msg = EmailMessage(
            to="user@example.com",
            subject="Hello",
            html_body="<p>Hi</p>",
            text_body="Hi",
        )
        assert msg.to == "user@example.com"
        assert msg.subject == "Hello"
        assert msg.html_body == "<p>Hi</p>"
        assert msg.text_body == "Hi"
        assert msg.from_address == ""  # optional, defaults to empty

    def test_from_address_optional(self):
        msg = EmailMessage(
            to="a@b.com",
            subject="S",
            html_body="H",
            text_body="T",
            from_address="sender@b.com",
        )
        assert msg.from_address == "sender@b.com"


# ---------------------------------------------------------------------------
# ConsoleEmailBackend
# ---------------------------------------------------------------------------


class TestConsoleEmailBackend:
    @pytest.mark.asyncio
    async def test_send_does_not_raise(self):
        backend = ConsoleEmailBackend()
        msg = EmailMessage(
            to="user@example.com",
            subject="Test subject",
            html_body="<p>Hello</p>",
            text_body="Hello",
        )
        # Should log and never raise
        await backend.send(msg)

    @pytest.mark.asyncio
    async def test_send_logs_message(self, caplog):
        import logging
        backend = ConsoleEmailBackend()
        msg = EmailMessage(
            to="dev@example.com",
            subject="Verification",
            html_body="<b>verify</b>",
            text_body="please verify",
            from_address="no-reply@app.com",
        )
        with caplog.at_level(logging.INFO, logger="zeno.email"):
            await backend.send(msg)

        combined = "\n".join(caplog.messages)
        assert "dev@example.com" in combined
        assert "Verification" in combined


# ---------------------------------------------------------------------------
# SMTPBackend — provider presets
# ---------------------------------------------------------------------------


class TestSMTPBackendPresets:
    def test_gmail_preset(self):
        b = SMTPBackend.gmail(username="me@gmail.com", app_password="abcd efgh")
        assert b._hostname == "smtp.gmail.com"
        assert b._port == 587
        assert b._username == "me@gmail.com"
        assert b._password == "abcd efgh"
        assert b._start_tls is True
        assert b._use_tls is False

    def test_sendgrid_preset(self):
        b = SMTPBackend.sendgrid(api_key="SG.xxxx")
        assert b._hostname == "smtp.sendgrid.net"
        assert b._port == 587
        assert b._username == "apikey"
        assert b._password == "SG.xxxx"
        assert b._start_tls is True

    def test_ses_preset(self):
        b = SMTPBackend.ses(region="us-east-1", key_id="AKID", secret="secret")
        assert b._hostname == "email-smtp.us-east-1.amazonaws.com"
        assert b._port == 587
        assert b._username == "AKID"
        assert b._password == "secret"
        assert b._start_tls is True

    def test_mailgun_preset_us(self):
        b = SMTPBackend.mailgun(username="postmaster@mg.example.com", password="pw")
        assert b._hostname == "smtp.mailgun.org"
        assert b._port == 587
        assert b._start_tls is True

    def test_mailgun_preset_eu(self):
        b = SMTPBackend.mailgun(username="pm@mg.example.com", password="pw", eu=True)
        assert b._hostname == "smtp.eu.mailgun.org"

    def test_mailtrap_preset(self):
        b = SMTPBackend.mailtrap(api_token="tok123")
        assert b._hostname == "live.smtp.mailtrap.io"
        assert b._port == 587
        assert b._username == "api"
        assert b._password == "tok123"
        assert b._start_tls is True

    def test_postmark_preset(self):
        b = SMTPBackend.postmark(api_token="pm-token")
        assert b._hostname == "smtp.postmarkapp.com"
        assert b._port == 587
        assert b._username == "pm-token"
        assert b._password == "pm-token"
        assert b._start_tls is True

    def test_resend_preset(self):
        b = SMTPBackend.resend(api_key="re_xxxx")
        assert b._hostname == "smtp.resend.com"
        assert b._port == 465
        assert b._username == "resend"
        assert b._password == "re_xxxx"
        assert b._use_tls is True
        assert b._start_tls is False

    def test_custom_constructor(self):
        b = SMTPBackend(
            hostname="smtp.myhost.com",
            port=2525,
            username="user",
            password="pass",
            start_tls=True,
        )
        assert b._hostname == "smtp.myhost.com"
        assert b._port == 2525
        assert b._max_retries == 3  # default
        assert b._timeout == 30      # default


# ---------------------------------------------------------------------------
# SMTPBackend — MIME construction
# ---------------------------------------------------------------------------


class TestSMTPBackendMIME:
    def test_build_mime_has_two_parts(self):
        b = SMTPBackend.sendgrid(api_key="key")
        msg = EmailMessage(
            to="r@ex.com",
            subject="Sub",
            html_body="<b>hi</b>",
            text_body="hi",
            from_address="s@ex.com",
        )
        mime = b._build_mime(msg)
        assert mime["Subject"] == "Sub"
        assert mime["From"] == "s@ex.com"
        assert mime["To"] == "r@ex.com"
        # multipart/alternative with plain + html
        payloads = mime.get_payload()
        assert len(payloads) == 2
        assert payloads[0].get_content_type() == "text/plain"
        assert payloads[1].get_content_type() == "text/html"

    def test_html_part_is_last(self):
        """RFC 2046: preferred (richest) alternative must come last."""
        b = SMTPBackend.gmail(username="a@g.com", app_password="pw")
        msg = EmailMessage(to="b@ex.com", subject="S", html_body="<i>x</i>", text_body="x")
        mime = b._build_mime(msg)
        payloads = mime.get_payload()
        assert payloads[-1].get_content_type() == "text/html"


# ---------------------------------------------------------------------------
# SMTPBackend — send() + retry
# ---------------------------------------------------------------------------


class TestSMTPBackendSend:
    def _make_backend(self, max_retries=3, retry_base_delay=0.0):
        return SMTPBackend(
            hostname="smtp.example.com",
            port=587,
            username="u",
            password="p",
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
        )

    @pytest.mark.asyncio
    async def test_send_calls_aiosmtplib_send(self):
        backend = self._make_backend()
        msg = EmailMessage(
            to="r@ex.com",
            subject="S",
            html_body="<p>H</p>",
            text_body="T",
            from_address="s@ex.com",
        )

        mock_aiosmtplib = MagicMock()
        mock_aiosmtplib.send = AsyncMock(return_value=None)

        with patch.object(backend, "_send_with_retry", wraps=backend._send_with_retry):
            # Inject the mock aiosmtplib module
            mime = backend._build_mime(msg)
            await backend._send_with_retry(mock_aiosmtplib, mime, 3, 0.0)

        mock_aiosmtplib.send.assert_called_once()
        call_kwargs = mock_aiosmtplib.send.call_args
        assert call_kwargs[1]["hostname"] == "smtp.example.com"
        assert call_kwargs[1]["port"] == 587

    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self):
        """SMTPServerDisconnected is transient — should retry."""
        backend = self._make_backend(max_retries=3, retry_base_delay=0.0)
        msg = EmailMessage(to="r@ex.com", subject="S", html_body="H", text_body="T")
        mime = backend._build_mime(msg)

        # Simulate a transient error class
        class FakeSMTPServerDisconnected(Exception):
            pass

        attempt_count = 0

        async def fake_send(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise FakeSMTPServerDisconnected("disconnected")
            # Succeed on 3rd attempt

        mock_lib = MagicMock()
        mock_lib.send = fake_send

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await backend._send_with_retry(mock_lib, mime, 3, 0.0)

        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self):
        """SMTPAuthenticationError is permanent — must raise immediately."""
        backend = self._make_backend(max_retries=3, retry_base_delay=0.0)
        msg = EmailMessage(to="r@ex.com", subject="S", html_body="H", text_body="T")
        mime = backend._build_mime(msg)

        class FakeSMTPAuthenticationError(Exception):
            pass

        attempt_count = 0

        async def fake_send(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            exc = FakeSMTPAuthenticationError("535 auth failed")
            exc.__class__.__name__ = "SMTPAuthenticationError"
            raise exc

        # Patch type name so retry logic sees it as permanent
        FakeSMTPAuthenticationError.__name__ = "SMTPAuthenticationError"

        mock_lib = MagicMock()
        mock_lib.send = fake_send

        with pytest.raises(FakeSMTPAuthenticationError):
            await backend._send_with_retry(mock_lib, mime, 3, 0.0)

        # Must NOT retry — should only have been called once
        assert attempt_count == 1

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(self):
        """If all retries fail with a transient error, the last exception is raised."""
        backend = self._make_backend(max_retries=2, retry_base_delay=0.0)
        msg = EmailMessage(to="r@ex.com", subject="S", html_body="H", text_body="T")
        mime = backend._build_mime(msg)

        class FakeConnectionError(ConnectionError):
            pass

        async def fake_send(*args, **kwargs):
            raise FakeConnectionError("connection refused")

        mock_lib = MagicMock()
        mock_lib.send = fake_send

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(FakeConnectionError):
                await backend._send_with_retry(mock_lib, mime, 2, 0.0)

    @pytest.mark.asyncio
    async def test_import_error_when_aiosmtplib_missing(self):
        """send() raises ImportError with helpful message if aiosmtplib not installed."""
        backend = self._make_backend()
        msg = EmailMessage(to="r@ex.com", subject="S", html_body="H", text_body="T")

        with patch.dict("sys.modules", {"aiosmtplib": None}):
            with pytest.raises(ImportError, match="aiosmtplib"):
                await backend.send(msg)

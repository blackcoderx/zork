"""SMTP email backend for Cinder.

``SMTPBackend`` is a concrete ``EmailBackend`` implementation that uses
``aiosmtplib`` for async SMTP delivery. It ships with provider presets for
the most popular transactional email services so developers can get started
with a single line of configuration.

Requires the ``email`` optional dependency::

    pip install cinder[email]
    # or
    uv add cinder[email]

Quick start::

    from cinder.email import SMTPBackend

    # SendGrid
    app.email.use(SMTPBackend.sendgrid(api_key=os.getenv("SENDGRID_API_KEY")))

    # Gmail
    app.email.use(SMTPBackend.gmail(username="me@gmail.com", app_password="xxxx xxxx xxxx xxxx"))

    # Any custom SMTP server
    app.email.use(SMTPBackend(hostname="smtp.myhost.com", port=587, username="u", password="p"))
"""
from __future__ import annotations

import asyncio
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from .backends import EmailBackend, EmailMessage

logger = logging.getLogger("cinder.email.smtp")


class SMTPBackend(EmailBackend):
    """Async SMTP email backend with provider presets.

    Uses ``aiosmtplib`` to send emails without blocking the event loop.
    Supports both STARTTLS (port 587, default) and implicit TLS (port 465).

    Transient failures (server disconnects, connection errors, timeouts) are
    retried with exponential back-off. Permanent failures (authentication
    errors, rejected recipients) raise immediately without retry.

    Args:
        hostname: SMTP server hostname.
        port: SMTP port. Default 587 (STARTTLS).
        username: SMTP login username.
        password: SMTP login password or API key.
        use_tls: Use implicit TLS (port 465). Mutually exclusive with ``start_tls``.
        start_tls: Upgrade connection to TLS via STARTTLS (port 587). Default ``True``.
        timeout: Connection and command timeout in seconds. Default 30.
        max_retries: Maximum number of send attempts for transient failures. Default 3.
        retry_base_delay: Initial retry delay in seconds. Doubles on each attempt. Default 1.0.
    """

    def __init__(
        self,
        hostname: str,
        port: int = 587,
        username: str = "",
        password: str = "",
        use_tls: bool = False,
        start_tls: bool = True,
        timeout: int = 30,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        self._hostname = hostname
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._start_tls = start_tls
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    # ------------------------------------------------------------------
    # Provider presets
    # ------------------------------------------------------------------

    @classmethod
    def gmail(cls, *, username: str, app_password: str) -> "SMTPBackend":
        """Gmail / Google Workspace.

        Requires an **App Password** — not your regular account password.
        Generate one at: Google Account → Security → 2-Step Verification → App passwords.

        ``username`` is your full Gmail address (e.g. ``me@gmail.com``).
        """
        return cls(
            hostname="smtp.gmail.com",
            port=587,
            username=username,
            password=app_password,
            start_tls=True,
        )

    @classmethod
    def sendgrid(cls, *, api_key: str) -> "SMTPBackend":
        """SendGrid.

        ``api_key`` is your SendGrid API key. The SMTP username is always
        the literal string ``"apikey"``.
        """
        return cls(
            hostname="smtp.sendgrid.net",
            port=587,
            username="apikey",
            password=api_key,
            start_tls=True,
        )

    @classmethod
    def ses(cls, *, region: str, key_id: str, secret: str) -> "SMTPBackend":
        """Amazon SES (Simple Email Service).

        ``region`` is the AWS region (e.g. ``"us-east-1"``).
        ``key_id`` and ``secret`` are the **SMTP-specific** credentials —
        not your IAM access keys. Generate them in the SES console:
        Account dashboard → SMTP settings → Create SMTP credentials.
        """
        return cls(
            hostname=f"email-smtp.{region}.amazonaws.com",
            port=587,
            username=key_id,
            password=secret,
            start_tls=True,
        )

    @classmethod
    def mailgun(cls, *, username: str, password: str, eu: bool = False) -> "SMTPBackend":
        """Mailgun.

        ``username`` is typically ``postmaster@mg.yourdomain.com``.
        ``password`` is the SMTP password from your Mailgun domain settings.
        Set ``eu=True`` to use the EU region endpoint (``smtp.eu.mailgun.org``).
        """
        host = "smtp.eu.mailgun.org" if eu else "smtp.mailgun.org"
        return cls(
            hostname=host,
            port=587,
            username=username,
            password=password,
            start_tls=True,
        )

    @classmethod
    def mailtrap(cls, *, api_token: str) -> "SMTPBackend":
        """Mailtrap — email testing and staging.

        Best for local development and QA environments. Captures all outgoing
        emails in a sandbox inbox with spam scoring and HTML validation.

        ``api_token`` is your Mailtrap API token (found in Mailtrap → SMTP Settings).
        """
        return cls(
            hostname="live.smtp.mailtrap.io",
            port=587,
            username="api",
            password=api_token,
            start_tls=True,
        )

    @classmethod
    def postmark(cls, *, api_token: str) -> "SMTPBackend":
        """Postmark.

        ``api_token`` is your Postmark Server API Token — used as both
        SMTP username and password.
        """
        return cls(
            hostname="smtp.postmarkapp.com",
            port=587,
            username=api_token,
            password=api_token,
            start_tls=True,
        )

    @classmethod
    def resend(cls, *, api_key: str) -> "SMTPBackend":
        """Resend.

        Uses port 465 with implicit TLS (not STARTTLS). ``api_key`` is your
        Resend API key. The SMTP username is always the literal string ``"resend"``.
        """
        return cls(
            hostname="smtp.resend.com",
            port=465,
            username="resend",
            password=api_key,
            use_tls=True,
            start_tls=False,
        )

    # ------------------------------------------------------------------
    # Send implementation
    # ------------------------------------------------------------------

    def _build_mime(self, message: EmailMessage) -> MIMEMultipart:
        """Build a ``multipart/alternative`` MIME message.

        Per RFC 2046, the preferred (HTML) part must come last.
        Email clients display the last part they can render.
        """
        mime = MIMEMultipart("alternative")
        mime["Subject"] = message.subject
        mime["From"] = message.from_address
        mime["To"] = message.to
        # Plain-text first (fallback for clients that can't render HTML)
        mime.attach(MIMEText(message.text_body, "plain", "utf-8"))
        # HTML second (preferred by capable clients)
        mime.attach(MIMEText(message.html_body, "html", "utf-8"))
        return mime

    async def send(self, message: EmailMessage) -> None:
        """Send ``message`` via SMTP with retry on transient failures.

        Raises:
            ImportError: If ``aiosmtplib`` is not installed (``cinder[email]`` extra).
            Exception: On permanent failure after all retries are exhausted.
        """
        try:
            import aiosmtplib
        except ImportError as exc:
            raise ImportError(
                "aiosmtplib is required for SMTPBackend. "
                "Install it with: pip install cinder[email]"
            ) from exc

        mime = self._build_mime(message)
        await self._send_with_retry(aiosmtplib, mime, self._max_retries, self._retry_base_delay)

    async def _send_with_retry(
        self,
        aiosmtplib: Any,
        mime: MIMEMultipart,
        retries_left: int,
        delay: float,
    ) -> None:
        """Internal retry loop with exponential back-off.

        Permanent errors (auth failure, recipients refused) are re-raised
        immediately. Transient errors trigger a sleep + retry.
        """
        _PERMANENT = ("SMTPAuthenticationError", "SMTPRecipientsRefused", "SMTPSenderRefused")
        try:
            await asyncio.wait_for(
                aiosmtplib.send(
                    mime,
                    hostname=self._hostname,
                    port=self._port,
                    username=self._username or None,
                    password=self._password or None,
                    use_tls=self._use_tls,
                    start_tls=self._start_tls,
                ),
                timeout=float(self._timeout),
            )
        except asyncio.TimeoutError as exc:
            if retries_left <= 1:
                raise
            logger.warning(
                "SMTP timeout sending to %s (retries left: %d) — retrying in %.1fs",
                mime["To"], retries_left - 1, delay,
            )
            await asyncio.sleep(delay)
            await self._send_with_retry(aiosmtplib, mime, retries_left - 1, delay * 2)
        except Exception as exc:
            exc_type = type(exc).__name__
            if exc_type in _PERMANENT:
                # Auth / recipient errors — retrying won't help
                logger.error(
                    "Permanent SMTP error (%s) sending to %s: %s",
                    exc_type, mime["To"], exc,
                )
                raise
            if retries_left <= 1:
                logger.error(
                    "SMTP send failed after all retries (to=%s): %s", mime["To"], exc,
                )
                raise
            logger.warning(
                "Transient SMTP error (%s) sending to %s — retrying in %.1fs (retries left: %d)",
                exc_type, mime["To"], delay, retries_left - 1,
            )
            await asyncio.sleep(delay)
            await self._send_with_retry(aiosmtplib, mime, retries_left - 1, delay * 2)

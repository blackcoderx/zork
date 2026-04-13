"""Core email abstractions for Cinder.

``EmailBackend`` is the abstract base class every backend must implement.
``EmailMessage`` is the data class passed to ``send()``.
``ConsoleEmailBackend`` is the zero-dependency fallback used when no backend
is configured — it logs the message to stdout so developers can inspect emails
during local development without any SMTP setup.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger("cinder.email")


@dataclass
class EmailMessage:
    """Represents a single outbound email.

    ``from_address`` is optional at construction time — ``_EmailConfig.send()``
    fills it in from the configured default before dispatching.

    Example::

        from cinder.email import EmailMessage

        msg = EmailMessage(
            to="user@example.com",
            subject="Welcome!",
            html_body="<p>Thanks for signing up.</p>",
            text_body="Thanks for signing up.",
        )
        await app.email.send(msg)
    """

    to: str
    subject: str
    html_body: str
    text_body: str
    from_address: str = field(default="")


class EmailBackend(ABC):
    """Abstract base class for Cinder email backends.

    Subclass this to integrate any delivery mechanism — SMTP, HTTP API,
    in-memory queue, etc. The only required method is ``send``.

    Example (custom HTTP API backend)::

        from cinder.email import EmailBackend, EmailMessage
        import httpx

        class PostmarkHTTPBackend(EmailBackend):
            def __init__(self, server_token: str):
                self._token = server_token

            async def send(self, message: EmailMessage) -> None:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        "https://api.postmarkapp.com/email",
                        headers={"X-Postmark-Server-Token": self._token},
                        json={
                            "From": message.from_address,
                            "To": message.to,
                            "Subject": message.subject,
                            "HtmlBody": message.html_body,
                            "TextBody": message.text_body,
                        },
                    )

        app.email.use(PostmarkHTTPBackend(server_token=os.getenv("POSTMARK_TOKEN")))
    """

    @abstractmethod
    async def send(self, message: EmailMessage) -> None:
        """Send ``message``.

        Raise on permanent failure (e.g. ``SMTPAuthenticationError``). For
        transient failures, implement retry logic inside this method — see
        ``SMTPBackend._send_with_retry()`` for the reference implementation.
        """


class ConsoleEmailBackend(EmailBackend):
    """Development fallback — logs email content to the console.

    Used automatically when no backend is configured via ``app.email.use(...)``.
    No dependencies, no network calls. Every outbound email appears in the
    server logs so developers can inspect content and links during local dev.
    """

    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            " EMAIL (console — configure app.email.use(...))\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            " From:    %s\n"
            " To:      %s\n"
            " Subject: %s\n"
            "────────────────────────────────────────\n"
            "%s\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            message.from_address or "(not set)",
            message.to,
            message.subject,
            message.text_body,
        )

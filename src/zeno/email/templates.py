"""Built-in email templates for Cinder's auth flows.

Each function returns a ``(subject, html_body, text_body)`` 3-tuple.
Templates use inline styles only — no CDN, no external resources, no
template engine dependency. They work in every major email client.

**Customising templates**

You are not required to use these templates. Override any of them on
``app.email`` using the ``on_password_reset``, ``on_verification``, and
``on_welcome`` methods:

.. code-block:: python

    # Plain f-string override
    def my_reset(ctx):
        url = ctx["reset_url"]
        return (
            "Reset your password",
            f"<h1>Click to reset</h1><a href='{url}'>{url}</a>",
            f"Reset link: {url}",
        )

    app.email.on_password_reset(my_reset)

    # Jinja2 override (install jinja2 separately)
    from jinja2 import Environment, FileSystemLoader

    jinja = Environment(loader=FileSystemLoader("templates/email"))

    def jinja_reset(ctx):
        html = jinja.get_template("reset.html").render(**ctx)
        text = jinja.get_template("reset.txt").render(**ctx)
        return "Reset your password", html, text

    app.email.on_password_reset(jinja_reset)

The ``ctx`` dict passed to your callable always contains the same keys
documented on each function below — nothing hidden, nothing extra.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Shared style helpers
# ---------------------------------------------------------------------------

_BASE_STYLE = (
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "Helvetica, Arial, sans-serif; font-size: 16px; line-height: 1.6; color: #1a1a1a;"
)

_BUTTON_STYLE = (
    "display: inline-block; padding: 12px 24px; background: #2563eb; "
    "color: #ffffff !important; text-decoration: none; border-radius: 6px; "
    "font-weight: 600; font-size: 15px;"
)

_CONTAINER_STYLE = (
    "max-width: 560px; margin: 40px auto; padding: 32px; "
    "border: 1px solid #e5e7eb; border-radius: 8px; background: #ffffff;"
)

_FOOTER_STYLE = (
    "margin-top: 32px; padding-top: 16px; border-top: 1px solid #e5e7eb; "
    "font-size: 13px; color: #6b7280;"
)


def _html_wrapper(app_name: str, body: str, footer: str = "") -> str:
    """Wrap ``body`` in a minimal email-safe HTML shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{app_name}</title>
</head>
<body style="margin: 0; padding: 0; background: #f3f4f6; {_BASE_STYLE}">
  <div style="{_CONTAINER_STYLE}">
    <p style="margin: 0 0 8px 0; font-size: 13px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em;">{app_name}</p>
    {body}
    {f'<div style="{_FOOTER_STYLE}">{footer}</div>' if footer else ''}
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Password-reset template
# ---------------------------------------------------------------------------

def password_reset_email(
    reset_url: str,
    app_name: str = "Your App",
    expiry_minutes: int = 60,
) -> tuple[str, str, str]:
    """Build the password-reset email.

    Args:
        reset_url: The full URL the user should visit to reset their password.
        app_name: Your application's name — shown in the email header.
        expiry_minutes: How long the link is valid (for display only, default 60).

    Returns:
        ``(subject, html_body, text_body)``

    Context dict passed to custom template overrides::

        {
            "reset_url": str,
            "app_name": str,
            "expiry_minutes": int,
        }
    """
    subject = f"Reset your {app_name} password"

    body_html = f"""
    <h2 style="margin: 0 0 16px 0; font-size: 22px; font-weight: 700;">Reset your password</h2>
    <p style="margin: 0 0 24px 0; color: #374151;">
      We received a request to reset the password for your <strong>{app_name}</strong> account.
      Click the button below to choose a new password.
    </p>
    <p style="margin: 0 0 24px 0;">
      <a href="{reset_url}" style="{_BUTTON_STYLE}">Reset Password</a>
    </p>
    <p style="margin: 0; color: #6b7280; font-size: 14px;">
      This link expires in <strong>{expiry_minutes} minutes</strong>.
      If you didn't request a password reset, you can safely ignore this email —
      your password will not be changed.
    </p>
    """

    footer_html = (
        f"If the button above doesn't work, copy and paste this URL into your browser:<br>"
        f"<a href=\"{reset_url}\" style=\"color: #2563eb; word-break: break-all;\">{reset_url}</a>"
    )

    html_body = _html_wrapper(app_name, body_html, footer_html)

    text_body = (
        f"Reset your {app_name} password\n"
        f"{'=' * 40}\n\n"
        f"We received a request to reset the password for your {app_name} account.\n\n"
        f"Click the link below to choose a new password:\n"
        f"{reset_url}\n\n"
        f"This link expires in {expiry_minutes} minutes.\n\n"
        f"If you didn't request a password reset, you can safely ignore this email."
    )

    return subject, html_body, text_body


# ---------------------------------------------------------------------------
# Email-verification template
# ---------------------------------------------------------------------------

def email_verification_email(
    verify_url: str,
    app_name: str = "Your App",
) -> tuple[str, str, str]:
    """Build the email-verification email sent after registration.

    Args:
        verify_url: The full URL the user should visit to verify their address.
        app_name: Your application's name.

    Returns:
        ``(subject, html_body, text_body)``

    Context dict passed to custom template overrides::

        {
            "verify_url": str,
            "app_name": str,
        }
    """
    subject = f"Verify your {app_name} email address"

    body_html = f"""
    <h2 style="margin: 0 0 16px 0; font-size: 22px; font-weight: 700;">Verify your email address</h2>
    <p style="margin: 0 0 24px 0; color: #374151;">
      Thanks for signing up for <strong>{app_name}</strong>!
      Please verify your email address to get started.
    </p>
    <p style="margin: 0 0 24px 0;">
      <a href="{verify_url}" style="{_BUTTON_STYLE}">Verify Email Address</a>
    </p>
    <p style="margin: 0; color: #6b7280; font-size: 14px;">
      This link expires in 24 hours.
      If you didn't create an account, you can safely ignore this email.
    </p>
    """

    footer_html = (
        f"If the button above doesn't work, copy and paste this URL into your browser:<br>"
        f"<a href=\"{verify_url}\" style=\"color: #2563eb; word-break: break-all;\">{verify_url}</a>"
    )

    html_body = _html_wrapper(app_name, body_html, footer_html)

    text_body = (
        f"Verify your {app_name} email address\n"
        f"{'=' * 40}\n\n"
        f"Thanks for signing up for {app_name}!\n"
        f"Please verify your email address by visiting the link below:\n\n"
        f"{verify_url}\n\n"
        f"This link expires in 24 hours.\n"
        f"If you didn't create an account, you can safely ignore this email."
    )

    return subject, html_body, text_body


# ---------------------------------------------------------------------------
# Welcome template
# ---------------------------------------------------------------------------

def welcome_email(
    user_email: str,
    app_name: str = "Your App",
) -> tuple[str, str, str]:
    """Build a welcome email sent after successful registration.

    This template is **opt-in** — it is not sent automatically unless the
    developer explicitly calls ``app.email.send(...)`` from a hook, or
    sets ``Auth(send_welcome_email=True)`` (future feature).

    Args:
        user_email: The new user's email address (used for personalisation).
        app_name: Your application's name.

    Returns:
        ``(subject, html_body, text_body)``

    Context dict passed to custom template overrides::

        {
            "user_email": str,
            "app_name": str,
        }
    """
    subject = f"Welcome to {app_name}!"

    body_html = f"""
    <h2 style="margin: 0 0 16px 0; font-size: 22px; font-weight: 700;">Welcome to {app_name}! 🎉</h2>
    <p style="margin: 0 0 16px 0; color: #374151;">
      Hi {user_email},
    </p>
    <p style="margin: 0 0 24px 0; color: #374151;">
      Your account has been created. We're glad to have you on board.
    </p>
    <p style="margin: 0; color: #6b7280; font-size: 14px;">
      If you have any questions, just reply to this email — we're always happy to help.
    </p>
    """

    html_body = _html_wrapper(app_name, body_html)

    text_body = (
        f"Welcome to {app_name}!\n"
        f"{'=' * 40}\n\n"
        f"Hi {user_email},\n\n"
        f"Your account has been created. We're glad to have you on board.\n\n"
        f"If you have any questions, just reply to this email — we're always happy to help."
    )

    return subject, html_body, text_body

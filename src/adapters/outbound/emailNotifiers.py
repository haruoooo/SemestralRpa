"""E-mail adapters: SMTP (Mailtrap sandbox in the project) and console (saves .eml files, sends nothing)."""

import smtplib
from email import policy
import socket
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from src.domain.agenda import OutgoingEmail
from src.domain.exceptions import NotificationRejectedError, NotificationUnavailableError
from src.infrastructure.timeProvider import nowLocal


# Python folds long non-ASCII headers into broken encoded-words ("=?utf-8?q??="), which mail clients show
# as garbage in the subject. With a 998-char line limit (RFC 5322 maximum) the subject is never folded.
_MAIL_POLICY = policy.SMTP.clone(max_line_length=998)


def buildMimeMessage(email: OutgoingEmail, sender: str) -> EmailMessage:
    message = EmailMessage(policy=_MAIL_POLICY)
    message["From"] = sender
    message["To"] = email.to
    message["Subject"] = email.subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="foradopico.example")
    message.set_content(email.textBody)
    message.add_alternative(email.htmlBody, subtype="html")
    for attachment in email.attachments:
        mainType, rest = attachment.mimeType.split("/", 1)
        subType, *rawParams = [part.strip() for part in rest.split(";")]
        params = dict(param.split("=", 1) for param in rawParams if "=" in param)
        if mainType == "text":
            params.setdefault("charset", "utf-8")  # Without it, clients read the accents of the .ics wrong
        message.add_attachment(attachment.content, maintype=mainType, subtype=subType, filename=attachment.fileName, params=params)
    return message


def maskEmail(address: str) -> str:
    """LGPD: a***@domain, for operator-facing output."""
    user, _, domain = address.partition("@")
    return f"{user[:1]}***@{domain}" if domain else "***"


class SmtpNotifier:
    channel = "email"

    def __init__(self, host: str, port: int, user: str, password: str, sender: str, timeoutSeconds: float, minIntervalSeconds: float = 0.0):
        self._host, self._port, self._user, self._password = host, port, user, password
        self._sender = sender
        self._timeout = timeoutSeconds
        self._minInterval = minIntervalSeconds
        self._lastSentAt = 0.0

    def send(self, email: OutgoingEmail) -> None:
        wait = self._minInterval - (time.monotonic() - self._lastSentAt)
        if wait > 0:  # Respects the provider rate limit (Mailtrap free plan)
            time.sleep(wait)
        message = buildMimeMessage(email, self._sender)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as server:
                server.starttls()
                if self._user:
                    server.login(self._user, self._password)
                server.send_message(message)
        except smtplib.SMTPRecipientsRefused as error:
            raise NotificationRejectedError("Recipient refused by the mail server") from error
        except smtplib.SMTPAuthenticationError as error:
            raise NotificationUnavailableError(f"SMTP authentication failed (check SMTP_USER/SMTP_PASSWORD): {error.smtp_code}") from error
        except smtplib.SMTPResponseException as error:
            detail = error.smtp_error.decode("utf-8", "replace") if isinstance(error.smtp_error, bytes) else str(error.smtp_error)
            raise NotificationUnavailableError(f"SMTP answered {error.smtp_code} {detail[:120]}") from error
        except (smtplib.SMTPException, socket.timeout, OSError) as error:
            raise NotificationUnavailableError(f"SMTP unreachable: {type(error).__name__}") from error
        finally:
            self._lastSentAt = time.monotonic()


class ConsoleNotifier:
    """Development mode: prints a masked line and saves the full message as .eml (opens in Outlook/Thunderbird)."""

    channel = "email"

    def __init__(self, outputDir: Path, sender: str):
        self._outputDir = outputDir
        self._sender = sender
        self._count = 0

    def send(self, email: OutgoingEmail) -> None:
        self._outputDir.mkdir(parents=True, exist_ok=True)
        self._count += 1
        target = self._outputDir / f"mail{nowLocal().strftime('%Y%m%d%H%M%S')}{self._count:03d}.eml"
        target.write_bytes(bytes(buildMimeMessage(email, self._sender)))
        print(f"[E-mail não enviado: modo console] Para {maskEmail(email.to)} · {email.subject} · salvo em {target}")

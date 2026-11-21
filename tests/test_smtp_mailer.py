import email
import smtplib
import socketserver
import threading
from email import policy

import pytest

from tms_vision import mailer, smtp_mailer

SMTP_ENV = {
    "TMS_SMTP_HOST": "smtp.example.org",
    "TMS_SMTP_FROM": "Cabinet Martin <contact@cabinet.example>",
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "TMS_MAILER", "TMS_SMTP_HOST", "TMS_SMTP_PORT", "TMS_SMTP_SECURE", "TMS_SMTP_STARTTLS",
        "TMS_SMTP_USER", "TMS_SMTP_PASS", "TMS_SMTP_FROM", "TMS_SMTP_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)


def _configure(monkeypatch, **overrides):
    monkeypatch.setenv("TMS_MAILER", "smtp")
    for name, value in {**SMTP_ENV, **overrides}.items():
        monkeypatch.setenv(name, value)


def _message(**overrides):
    base = dict(to="patient@example.com", subject="Vos exercices", text="Bonjour",
                html="<p>Bonjour</p>")
    return mailer.OutgoingMessage(**{**base, **overrides})


# --- configuration ---------------------------------------------------------------------------

def test_smtp_is_selected_by_name(monkeypatch):
    _configure(monkeypatch)
    assert isinstance(mailer.get_mailer(), smtp_mailer.SmtpMailer)


def test_defaults(monkeypatch):
    _configure(monkeypatch)
    settings = smtp_mailer.SmtpSettings.from_env()
    assert (settings.port, settings.secure, settings.starttls) == (587, False, True)
    assert settings.user == "" and settings.timeout == 15.0


def test_secure_defaults_to_port_465(monkeypatch):
    _configure(monkeypatch, TMS_SMTP_SECURE="true")
    assert smtp_mailer.SmtpSettings.from_env().port == 465


@pytest.mark.parametrize(
    "overrides, missing",
    [
        ({"TMS_SMTP_HOST": " "}, "TMS_SMTP_HOST"),
        ({"TMS_SMTP_FROM": ""}, "TMS_SMTP_FROM"),
        ({"TMS_SMTP_FROM": "pas-une-adresse"}, "TMS_SMTP_FROM"),
        ({"TMS_SMTP_PORT": "abc"}, "TMS_SMTP_PORT"),
        ({"TMS_SMTP_PORT": "70000"}, "TMS_SMTP_PORT"),
        ({"TMS_SMTP_SECURE": "peut-être"}, "TMS_SMTP_SECURE"),
        ({"TMS_SMTP_TIMEOUT": "0"}, "TMS_SMTP_TIMEOUT"),
    ],
)
def test_invalid_configuration_is_refused(monkeypatch, overrides, missing):
    _configure(monkeypatch, **overrides)
    with pytest.raises(mailer.MailerError, match=missing):
        mailer.get_mailer()


def test_mime_has_text_and_html_parts_and_reply_to(monkeypatch):
    _configure(monkeypatch)
    settings = smtp_mailer.SmtpSettings.from_env()
    mime = smtp_mailer.build_mime(settings, _message(reply_to="dr.martin@example.com"))
    assert mime["From"] == SMTP_ENV["TMS_SMTP_FROM"]
    assert mime["Reply-To"] == "dr.martin@example.com"
    assert mime["Message-ID"].endswith("@cabinet.example>")
    assert mime.get_body(("plain",)).get_content().strip() == "Bonjour"
    assert "<p>Bonjour</p>" in mime.get_body(("html",)).get_content()


def test_mime_without_html_is_plain_text_only(monkeypatch):
    _configure(monkeypatch)
    mime = smtp_mailer.build_mime(
        smtp_mailer.SmtpSettings.from_env(), _message(html=None)
    )
    assert not mime.is_multipart()


def test_header_injection_is_refused(monkeypatch):
    _configure(monkeypatch)
    service = smtp_mailer.SmtpMailer()
    with pytest.raises(mailer.MailerError):
        service.send(_message(subject="Bonjour\r\nBcc: autre@example.com"))


# --- dialogue avec le serveur (faux smtplib) ---------------------------------------------------

class _FakeSMTP:
    instances: list = []
    fail_login = False
    fail_connect = False

    def __init__(self, host, port, timeout=None, context=None):
        if type(self).fail_connect:
            raise ConnectionRefusedError("boom")
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls: list = []
        type(self).instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append(("starttls", context is not None))

    def login(self, user, password):
        if type(self).fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"mot-de-passe-secret refus\xc3\xa9")
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.calls.append(("send", message["To"]))


class _FakeSMTPSSL(_FakeSMTP):
    pass


@pytest.fixture
def fake_smtp(monkeypatch):
    _FakeSMTP.instances = []
    _FakeSMTP.fail_login = False
    _FakeSMTP.fail_connect = False
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTPSSL)
    return _FakeSMTP


def test_send_uses_starttls_then_login_then_sends(monkeypatch, fake_smtp):
    _configure(monkeypatch, TMS_SMTP_USER="contact@cabinet.example", TMS_SMTP_PASS="secret")
    mailer.get_mailer().send(_message())
    (server,) = fake_smtp.instances
    assert type(server) is _FakeSMTP and (server.host, server.port) == ("smtp.example.org", 587)
    assert server.calls == [
        ("starttls", True),
        ("login", "contact@cabinet.example", "secret"),
        ("send", "patient@example.com"),
    ]
    assert server.context is None  # la vérification du certificat passe par starttls(context=)


def test_send_secure_uses_ssl_with_default_verification(monkeypatch, fake_smtp):
    _configure(monkeypatch, TMS_SMTP_SECURE="true")
    mailer.get_mailer().send(_message())
    (server,) = fake_smtp.instances
    assert isinstance(server, _FakeSMTPSSL) and server.port == 465
    assert server.context is not None and server.context.check_hostname
    assert server.calls == [("send", "patient@example.com")]


def test_send_without_user_skips_login_and_starttls_can_be_off(monkeypatch, fake_smtp):
    _configure(monkeypatch, TMS_SMTP_STARTTLS="false")
    mailer.get_mailer().send(_message())
    assert fake_smtp.instances[0].calls == [("send", "patient@example.com")]


def test_rejected_password_gives_a_hint_without_leaking_secrets(monkeypatch, fake_smtp):
    fake_smtp.fail_login = True
    _configure(monkeypatch, TMS_SMTP_USER="u", TMS_SMTP_PASS="mot-de-passe-secret")
    with pytest.raises(mailer.MailerError) as error:
        mailer.get_mailer().send(_message())
    assert "mot de passe d'application" in str(error.value)
    assert "mot-de-passe-secret" not in str(error.value)


def test_unreachable_server_is_a_mailer_error(monkeypatch, fake_smtp):
    fake_smtp.fail_connect = True
    _configure(monkeypatch)
    with pytest.raises(mailer.MailerError, match="ConnectionRefusedError"):
        mailer.get_mailer().send(_message())


# --- vrai dialogue SMTP sur une prise locale (sans TLS, comme Mailpit en développement) ----------

class _Handler(socketserver.StreamRequestHandler):
    def _say(self, text):
        self.wfile.write(text.encode() + b"\r\n")

    def handle(self):
        server = self.server
        self._say("220 test ESMTP")
        in_data = False
        data: list[bytes] = []
        while line := self.rfile.readline():
            if in_data:
                if line == b".\r\n":
                    in_data = False
                    server.received.append(b"".join(data))
                    data = []
                    self._say("250 OK")
                else:
                    data.append(line)
                continue
            command = line.decode(errors="replace").strip().upper()
            if command.startswith(("EHLO", "HELO")):
                self._say("250 test")
            elif command.startswith(("MAIL", "RCPT", "RSET", "NOOP")):
                self._say("250 OK")
            elif command == "DATA":
                self._say("354 go")
                in_data = True
            elif command == "QUIT":
                self._say("221 bye")
                return
            else:
                self._say("502 non géré")


@pytest.fixture
def local_server():
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_message_really_reaches_a_local_server(monkeypatch, local_server):
    _configure(
        monkeypatch,
        TMS_SMTP_HOST="127.0.0.1",
        TMS_SMTP_PORT=str(local_server.server_address[1]),
        TMS_SMTP_STARTTLS="false",
    )
    mailer.get_mailer().send(_message(subject="Vos exercices é", reply_to="dr@example.com"))
    (raw,) = local_server.received
    parsed = email.message_from_bytes(raw, policy=policy.default)
    assert parsed["To"] == "patient@example.com"
    assert parsed["Subject"] == "Vos exercices é"
    assert parsed["Reply-To"] == "dr@example.com"
    assert parsed.get_body(("plain",)).get_content().strip() == "Bonjour"
    assert parsed.get_body(("html",)) is not None


# --- version HTML du message de partage --------------------------------------------------------

def test_share_message_html_escapes_content_and_links_the_url():
    message = mailer.build_share_message(
        to="patient@example.com",
        share_url="https://cabinet.example/e/1?a=1&b=2",
        practitioner_name="Dr <Martin>",
        message="Bonjour\nà bientôt",
        exercise_titles=["Étirement A & B", "Pont"],
    )
    assert "<Martin>" not in message.html and "Dr &lt;Martin&gt;" in message.html
    assert "<li>Étirement A &amp; B</li>" in message.html
    assert '<a href="https://cabinet.example/e/1?a=1&amp;b=2">' in message.html
    assert "Bonjour<br>à bientôt" in message.html
    assert "https://cabinet.example/e/1?a=1&b=2" in message.text

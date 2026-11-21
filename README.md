# Urlaubsplanung inkl. Vertretung

Kleine Web-App (Flask + SQLite) für Urlaubsplanung mit Vertretungsregelung
und automatischer E-Mail-Benachrichtigung der Vertretung.

## Funktionen

- **Anmeldung**: Registrieren mit Name, E-Mail, Team und Passwort ("wer bist du und zu wem gehörst du").
  Die erste registrierte Person wird automatisch Administrator:in.
- **Verwaltung**: Admins legen weitere Nutzer:innen an (Name, E-Mail, Team, Passwort, Rolle).
- **Urlaub eintragen**: Von/Bis mit Datumsauswahl sowie optionaler Hinweis.
- **Vertretung wählen**: Aus allen angelegten Nutzer:innen (außer dir selbst).
- **Mail an die Vertretung**: Sobald der Urlaub gespeichert wird, erhält die gewählte Vertretung
  eine E-Mail mit Urlauber:in, Team, **Von/Bis** und Hinweis.
- **Übersicht**: "Mein Urlaub" (mit Löschen) und "Vertretung für andere".

## Schnellstart

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # Werte anpassen (SECRET_KEY, SMTP)
export $(grep -v '^#' .env | xargs)   # oder Werte direkt als Umgebungsvariablen setzen

python app.py                    # Startet auf http://127.0.0.1:5000
```

Beim ersten Start wird die SQLite-Datenbank `urlaubsplanung.db` automatisch angelegt
(manuell: `python -c "from app import init_db; init_db()"`).

Workflow: Auf **/register** registrieren → erste Person ist automatisch Admin → unter
**Nutzer:innen** die Kolleg:innen anlegen → Urlaub eintragen und Vertretung wählen.

## E-Mail-Versand (SMTP)

Die Vertretungs-Mail wird per SMTP versendet. Konfiguration über Umgebungsvariablen:

| Variable        | Bedeutung                                  | Beispiel              |
|-----------------|--------------------------------------------|-----------------------|
| `SMTP_HOST`     | SMTP-Server                                | `smtp.gmail.com`      |
| `SMTP_PORT`     | Port (Standard 587)                        | `587`                 |
| `SMTP_USE_TLS`  | STARTTLS verwenden (`1`/`0`, Standard `1`) | `1`                   |
| `SMTP_USER`     | Benutzername                               | `planung@example.com` |
| `SMTP_PASSWORD` | Passwort / App-Passwort                    | `********`            |
| `SMTP_FROM`     | Absenderadresse                            | `planung@example.com` |

Ohne `SMTP_HOST` läuft die App trotzdem: Die Mail wird **nur im Server-Log ausgegeben**
(Testbetrieb), es geht keine echte Mail raus.

Beispiel Gmail: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587` und ein **App-Passwort**
(Google-Konto → Sicherheit → 2-Faktor → App-Passwörter).

## Sicherheit

- Passwörter werden gehasht (`werkzeug.security`, PBKDF2).
- Session-basierte Anmeldung; geschützte Seiten per Decorator.
- `SECRET_KEY` in der Produktion unbedingt auf einen eigenen Zufallswert setzen.

## Struktur

```
app.py            # Flask-App: Anmeldung, Urlaub, Vertretung, Mail, Verwaltung
templates/        # Jinja2-Templates (Deutsch)
static/style.css  # Styles ohne externe Abhängigkeiten
```

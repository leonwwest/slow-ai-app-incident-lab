# Incident Runbook: Langsame AI-/Web-App analysieren

Dieses Runbook beschreibt systematisch, wie man eine langsame, teure oder
instabile AI-/Web-App untersucht. Jeder Schritt enthält konkrete Checks,
Beispielergebnisse und Interpretationshilfen.

Im Kontext dieses Labs werden die Schritte gegen die lokal laufende App
angewendet. Starte die App (`python run.py`), führe einen Load-Test aus
(`k6 run k6/load-test.js`) und arbeite dann die Schritte nacheinander ab.
Die Queries aus Schritt 2/3/8 findest du in `sql/observability_queries.sql`
bzw. als fertigen Report via `python scripts/analyze.py`.

---

## Schritt 1: Incident einordnen

Fragen:

- Seit wann ist die App langsam?
- Betrifft es alle Nutzer oder nur einzelne?
- Betrifft es alle Endpoints oder nur bestimmte?
- Gab es ein neues Deployment?
- Gab es Änderungen an API-Key, IAM, DNS, Netzwerk oder Skalierung?
- Gibt es erhöhte Cloud-Kosten?

Ergebnis:

```text
Incident Start:      [Zeitpunkt]
Betroffene Services: [API, DB, AI Provider, Frontend]
Impact:              [niedrig/mittel/hoch]
User Impact:         [Beschreibung]
Deployment:          [z. B. v1.4.0]
```

Im Lab: siehe `deployment_version` in der `/health`-Antwort und in jeder
Log-Zeile. Der Default ist `v1.4.0` (die „schlechte" Version).

---

## Schritt 2: P95/P99-Latenz prüfen

Prüfen:

- Welche Endpoints sind langsam?
- Ist P95 erhöht?
- Ist P99 extrem hoch?
- Gibt es einzelne Ausreißer?
- Ist die Latenz konstant hoch oder nur in Peaks?

Lokal ausführen:

```bash
python scripts/analyze.py            # enthält Query 1: P50/P95/P99 pro Endpoint
```

Oder direkt gegen die SQLite-DB (Query 1 in `sql/observability_queries.sql`,
Postgres-Fassung):

```sql
SELECT
  endpoint,
  COUNT(*) AS request_count,
  AVG(latency_ms) AS avg_latency_ms,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
  PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_latency_ms
FROM request_logs
WHERE timestamp >= NOW() - INTERVAL '1 hour'
GROUP BY endpoint
ORDER BY p95_latency_ms DESC;
```

Beispielanalyse:

```text
/health         P95: 80 ms
/chat           P95: 900 ms
/slow-chat      P95: 6.500 ms
/db-query       P95: 3.200 ms
```

Interpretation:

```text
/health ist schnell, also läuft die App grundsätzlich.
/chat/slow und /db-query sind langsam.
Problem liegt wahrscheinlich bei AI Provider oder Datenbank.
```

Bewertung P95/P99:

- P50 zeigt normale Nutzererfahrung.
- P95 zeigt schlechte Nutzererfahrung für die langsamsten 5 %.
- P99 zeigt Extremfälle und Produktionsprobleme.

Beispiel:

```text
P50: 350 ms    -> gut
P95: 2.800 ms  -> kritisch
P99: 7.500 ms  -> sehr kritisch
```

---

## Schritt 3: Error Rate prüfen

Formel:

```text
Error Rate = Fehlerhafte Requests / Alle Requests * 100
```

Beispiel:

```text
10 Fehler / 1.000 Requests = 1 % Error Rate
```

Bewertung:

```text
< 0.1 %     sehr gut
0.1-1 %     beobachten
1-5 %       kritisch
> 5 %       Incident
```

Lokal: `python scripts/analyze.py` enthält Query 2 (Error Rate pro Endpoint)
und Query 2b (Errors nach Endpoint / Status Code).

Status-Code-Klassifikation:

```text
401 / 403   IAM oder API-Key
429         Rate Limit
500         App-Bug
502/503/504 Upstream / Provider / Timeout
```

Beispiel:

```text
Gesamt Error Rate: 2.8 %
/chat Error Rate: 0.4 %
/chat/slow Error Rate: 6.2 %
/random-error Error Rate: 100.0 %
```

Interpretation:

```text
Fehler sind nicht global.
Problem konzentriert sich auf langsame oder externe Requests.
Viele 503/504 deuten auf Provider-Timeouts oder Upstream-Probleme.
429 deutet auf Rate Limit.
401 deutet auf API-Key/IAM.
```

---

## Schritt 4: Logs prüfen

Jeder Request erzeugt eine strukturierte JSON-Zeile auf stdout. Beispiel:

```json
{
  "timestamp": "2026-06-25T10:00:00.000000+00:00",
  "level": "info",
  "logger": "incident_lab.request",
  "message": "request.completed",
  "request_id": "req_123",
  "user_id": "user_42",
  "endpoint": "/chat/slow",
  "method": "POST",
  "status_code": 503,
  "latency_ms": 7200,
  "provider_latency_ms": 6800,
  "db_latency_ms": null,
  "tokens_used": null,
  "estimated_cost_usd": null,
  "error_message": "AI provider 503: upstream timeout",
  "deployment_version": "v1.4.0",
  "region": "eu-central-1"
}
```

Im Lab liegen die Logs zusätzlich als Zeilen in der Tabelle `request_logs`
(`data/incident_lab.db`). Damit lassen sich alle Checks auch per SQL
ausführen.

Prüfen:

- Gibt es wiederkehrende Fehler?
- Haben langsame Requests dieselbe Request-ID-Struktur?
- Kommen Fehler von App, DB oder externem Provider? (`error_message`,
  `provider_latency_ms`, `db_latency_ms`)
- Gibt es API-Key-Fehler? (`status_code = 401`, `error_message` enthält
  „api key")
- Gibt es Timeout-Meldungen? (`status_code = 503`, „timeout")
- Sind Token-Verbrauch oder Kosten auffällig? (`tokens_used`,
  `estimated_cost_usd`)

Beispiel-Queries gegen die lokale DB:

```bash
# Alle Fehler der letzten Stunde
sqlite3 data/incident_lab.db \
  "SELECT timestamp, endpoint, status_code, error_message
   FROM request_logs
   WHERE status_code >= 400 AND timestamp >= datetime('now','-1 hour')
   ORDER BY timestamp DESC LIMIT 20;"

# Langsamste Requests
sqlite3 data/incident_lab.db \
  "SELECT timestamp, endpoint, latency_ms, provider_latency_ms, db_latency_ms
   FROM request_logs
   ORDER BY latency_ms DESC LIMIT 10;"
```

---

## Schritt 5: Traces prüfen

Trace-Fragen:

- Wo verbringt der Request die meiste Zeit?
- Backend? Datenbank? Externer AI Provider? Auth Middleware? DNS Lookup?
  Cold Start?

Dieses Lab exportiert noch keine echten OTel-Traces (siehe
[Next Improvements](../README.md#next-improvements)), aber die Felder
`provider_latency_ms`, `db_latency_ms` und `latency_ms` in jeder Log-Zeile
bilden eine ausreichende Trace-Skizze:

```text
POST /chat/slow          latency_ms = 7175
├── auth_check                       (in simulate_provider_call)
├── ai_provider_request   provider_latency_ms = 6900
├── save_result_to_db     db_latency_ms         = 140 (via /db-query pattern)
└── response_serialization
Total: latency_ms ≈ provider_latency_ms + overhead
```

Beispiel-Trace (idealisierter Auszug):

```text
POST /chat/slow
├── auth_check                  25 ms
├── validate_input              10 ms
├── db_get_user                 80 ms
├── ai_provider_request       6900 ms
├── save_result_to_db          140 ms
└── response_serialization      20 ms
Total: 7175 ms
```

Interpretation:

```text
Der Hauptteil der Latenz liegt beim AI Provider.
Optimierung sollte dort beginnen: Timeout, Retry, Model-Auswahl,
Streaming, Caching.
```

Eine typische Heuristik aus den Log-Feldern:

```text
Wenn provider_latency_ms ≈ latency_ms  -> Provider ist der Bottleneck.
Wenn db_latency_ms     ≈ latency_ms  -> Datenbank ist der Bottleneck.
Wenn latency_ms >> provider_latency_ms + db_latency_ms -> Overhead
   (Middleware, Serialisierung, Queue, Cold Start).
```

---

## Schritt 6: IAM/API-Key prüfen

Typische Probleme:

- API-Key fehlt
- API-Key abgelaufen
- falscher Secret Name
- falsche Environment Variable
- falsche IAM-Rolle
- Secret wurde rotiert, App aber nicht neu deployed
- Rate Limit durch falschen Plan
- falsche Region oder falsches Projekt

Im Lab: lass `AI_API_KEY` in `.env` leer, um 401-Fehler auf `/chat` und
`/chat/slow` zu reproduzieren. Setze `AI_API_KEY=irgendwas` und starte die
App neu, um die Fehler verschwinden zu lassen.

Checks:

```text
- Ist AI_API_KEY gesetzt?                      (env / secret manager)
- Wird der richtige Key verwendet?
- Hat der Key Zugriff auf das Modell?
- Gibt es 401 oder 403 Fehler in den Logs?
- Gibt es 429 Rate Limits in den Logs?
- Wurde der Secret Manager geändert?
- Wurde nach Secret-Änderung neu deployed?
```

Beispielbefund:

```text
401 Errors seit Deployment v1.4.0.
Neue Version erwartet AI_API_KEY_V2, aber Secret heißt noch AI_API_KEY.
-> Secret nachziehen oder App neu deployen.
```

---

## Schritt 7: Netzwerk und DNS prüfen

Prüfen:

- DNS-Auflösung langsam?
- Provider-Endpoint erreichbar?
- Region falsch?
- TLS Handshake langsam?
- Proxy / VPN / Firewall?
- Egress-Probleme?
- Paketverlust?
- IPv6/IPv4-Probleme?

Checks:

```bash
nslookup api.simulated-ai-provider.com
dig api.simulated-ai-provider.com
curl -w "@k6/curl-format.txt" -o /dev/null -s https://api.simulated-ai-provider.com/health
traceroute api.simulated-ai-provider.com
```

Wichtige Werte (aus `k6/curl-format.txt`):

```text
dns_lookup     TCP/TLS/HTTP time to name resolution
tcp_connect    TCP connect time
tls_handshake  TLS handshake time
ttfb           Time To First Byte
total          Total time
http_code      HTTP status code
```

Interpretation:

```text
Wenn DNS oder TLS langsam ist, liegt das Problem eher bei Netzwerk/Provider.
Wenn TTFB langsam ist, liegt es oft beim Upstream-Service.
```

Im Lab ist der Provider nur simuliert (`api.simulated-ai-provider.com`
existiert nicht wirklich) - die Checks demonstrieren trotzdem die
Vorgehensweise gegen einen echten Provider.

---

## Schritt 8: Cloud-Kosten prüfen

Bei AI-Apps können Performanceprobleme und Kostenprobleme zusammenhängen.

Prüfen:

- Sind Requests gestiegen?
- Sind Tokens pro Request gestiegen?
- Gibt es Retry-Loops?
- Werden fehlgeschlagene Requests trotzdem berechnet?
- Gibt es unnötig lange Prompts?
- Nutzt die App ein teures Modell für einfache Aufgaben?
- Gibt es Abuse oder Bots?
- Werden Antworten gecached?

Lokal: `python scripts/analyze.py` enthält Query 3 (AI cost / tokens pro
User / Endpoint) und eine Kostenzusammenfassung pro Deployment-Version.

Postgres-Fassung (Query 3 in `sql/observability_queries.sql`):

```sql
SELECT
  user_id,
  endpoint,
  COUNT(*) AS ai_requests,
  SUM(tokens_used) AS total_tokens,
  ROUND(SUM(estimated_cost_usd), 4) AS total_cost_usd,
  ROUND(AVG(tokens_used), 2) AS avg_tokens_per_request,
  ROUND(AVG(latency_ms), 2) AS avg_latency_ms
FROM request_logs
WHERE timestamp >= NOW() - INTERVAL '24 hours'
  AND tokens_used IS NOT NULL
GROUP BY user_id, endpoint
ORDER BY total_cost_usd DESC
LIMIT 20;
```

Beispielbefund:

```text
Kosten pro Stunde sind von 0.80 USD auf 7.40 USD gestiegen.
Gleichzeitig stieg die P99-Latenz auf 9 Sekunden.
Logs zeigen Retry-Loops bei Provider-Timeouts.
```

Mögliche Maßnahmen:

```text
- Max Tokens begrenzen
- Retry-Limit setzen
- Timeout setzen
- günstigeres Modell für einfache Aufgaben
- Prompt kürzen
- Caching aktivieren
- Rate Limit pro User/IP
```

---

## Schritt 9: Skalierung prüfen

Prüfen:

- CPU-Auslastung
- RAM-Auslastung
- Container Restarts
- Queue Length
- Datenbankverbindungen
- Cold Starts
- Autoscaling-Regeln
- Max Instances / Min Instances
- Concurrency pro Instance

Typische Probleme:

```text
- zu wenige Instanzen
- zu niedrige Memory Limits
- keine Autoscaling-Regel
- DB Connection Pool zu klein
- DB Connection Pool zu groß
- Cold Starts bei Serverless
- eine langsame AI-Operation blockiert Worker
```

Im Lab läuft alles in einem Prozess, daher sind CPU/RAM-Auslastung über
`/health` nicht direkt sichtbar. Unter Load (`k6 run k6/load-test.js`)
erkennst du das Skalierungsverhalten dennoch: wenn `/chat`-Latenz steigt,
obwohl der Endpoint selbst schnell ist, ist der Worker durch parallele
`/chat/slow`-Aufrufe blockiert (Head-of-Line-Blocking).

Beispielbefund:

```text
CPU liegt bei 95 %.
P95 steigt parallel zur Request-Anzahl.
Autoscaling ist auf max 1 Instance begrenzt.
```

Maßnahme:

```text
Max Instances erhöhen.
Concurrency reduzieren oder Worker entkoppeln.
Background Queue für AI-Jobs nutzen.
```

---

## Schritt 10: Rollback prüfen

Rollback-Fragen:

- Gab es kurz vor dem Problem ein Deployment?
- Welche Version war vorher stabil?
- Gibt es Feature Flags?
- Ist ein Datenbank-Migration-Rollback nötig?
- Sind Secrets kompatibel?
- Kann man nur ein Feature deaktivieren?

Im Lab: setze `DEPLOYMENT_VERSION=v1.3.2` in `.env`, starte die App neu und
vergleiche die Kosten-/Latenz-/Error-Zusammenfassung pro Version aus
`python scripts/analyze.py`.

Rollback-Entscheidung:

```text
Rollback durchführen, wenn:
- Error Rate stark steigt
- P95/P99 stark steigt
- Kernfunktion nicht nutzbar ist
- Kosten unkontrolliert steigen
- Ursache nicht schnell gefunden wird
```

Beispiel:

```text
Neue Version v1.4.0 verursacht 503 Errors bei /chat/slow.
Rollback auf v1.3.2 reduziert Error Rate von 6.2 % auf 0.3 %.
```

---

## Schnellreferenz

```bash
# App starten
python run.py

# Load erzeugen
k6 run k6/load-test.js

# Report (P50/P95/P99, Error Rate, Kosten)
python scripts/analyze.py
python scripts/analyze.py --hours 24

# Kanonische SQL-Queries (Postgres-Dialekt)
# -> sql/observability_queries.sql

# Rohe Logs ansehen
Get-Content data/server.log -Tail 20        # Windows
tail -n 20 data/server.log                  # Linux/macOS

# Direkt gegen SQLite
sqlite3 data/incident_lab.db "SELECT endpoint, COUNT(*) FROM request_logs GROUP BY endpoint;"
```

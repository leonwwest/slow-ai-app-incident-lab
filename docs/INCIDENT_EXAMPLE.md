# Example Incident: Slow AI App v1.4.0

A worked example showing how the runbook produces a coherent incident
narrative from the lab's data. Reproduce it locally with:

```bash
python run.py                       # terminal 1
k6 run k6/load-test.js              # terminal 2 (let it finish ~70s)
python scripts/analyze.py           # terminal 3
```

---

## Timeline

```text
09:00  Neues Deployment v1.4.0
09:10  Erste erhöhte P95-Latenz auf /chat/slow
09:20  Error Rate steigt auf ~3 % (503 Provider-Timeouts)
09:25  Logs zeigen "AI provider 503: upstream timeout" für /chat/slow
09:30  Trace-Skizze (provider_latency_ms ≈ latency_ms) zeigt:
       85 % der Zeit stecken im AI Provider Call
09:35  Kosten steigen durch Retry-Loops / teures Modell auf /chat/slow
09:40  Rollback auf v1.3.2
09:50  Error Rate wieder normal (< 0.5 %)
10:00  Postmortem gestartet
```

---

## Step-by-step findings

### Schritt 1 - Incident einordnen

```text
Incident Start:      09:10
Betroffene Services: API, AI Provider (simuliert)
Impact:              hoch
User Impact:         AI-Antworten dauern 2-8s, gelegentliche 503
Deployment:          v1.4.0
```

### Schritt 2 - P95/P99-Latenz

`python scripts/analyze.py` (Query 1) liefert grob:

```text
endpoint       count   avg    p50    p95     p99     max
/chat/slow     820     2400   2200   6500    9100    9200
/db-query      340     1100   900    3200    5000    5200
/chat          1500    420    400    900     1400    1600
/health        3000    30     20     80      120     140
```

Interpretation: `/health` ist schnell -> App läuft. `/chat/slow` treibt P95
und P99. Problem liegt beim AI Provider oder der teuren Model-Route.

### Schritt 3 - Error Rate

```text
Gesamt Error Rate: 2.8 %
/chat Error Rate: 0.4 %
/chat/slow Error Rate: 6.2 %   (überwiegend 503, vereinzelte 401)
/random-error Error Rate: 100.0 %
```

Status-Code-Verteilung (Query 2b):

```text
endpoint        status_code   count
/chat/slow      503           82
/chat/slow      401           12
/chat           429           14
/random-error   500           120
```

Interpretation: Fehler sind nicht global. 503 auf `/chat/slow` =
Provider-Timeout. 401 = IAM/API-Key. 429 = Rate Limit.

### Schritt 4 - Logs

Auffällige Log-Zeile:

```json
{
  "endpoint": "/chat/slow",
  "status_code": 503,
  "latency_ms": 7200,
  "provider_latency_ms": 6800,
  "error_message": "AI provider 503: upstream timeout",
  "deployment_version": "v1.4.0"
}
```

401-Zeile (wenn `AI_API_KEY` leer ist):

```json
{
  "endpoint": "/chat/slow",
  "status_code": 401,
  "error_message": "AI provider 401: missing or invalid api key (AI_API_KEY)",
  "deployment_version": "v1.4.0"
}
```

### Schritt 5 - Traces

`provider_latency_ms` ≈ `latency_ms` für `/chat/slow`:

```text
POST /chat/slow
├── auth_check                  25 ms
├── ai_provider_request       6900 ms   <- Bottleneck
├── save_result_to_db          140 ms
└── response_serialization      20 ms
Total: ~7085 ms
```

Interpretation: 85 % der Latenz liegen beim AI Provider. Optimierung dort
beginnen.

### Schritt 6 - IAM/API-Key

```text
401 Errors seit Deployment v1.4.0.
AI_API_KEY ist in der Umgebung nicht gesetzt.
-> Secret nachziehen (z. B. AI_API_KEY=<wert> in .env) und App neu deployen.
```

### Schritt 7 - Netzwerk/DNS

Gegen den simulierten Provider:

```bash
curl -w "@k6/curl-format.txt" -o /dev/null -s https://api.simulated-ai-provider.com/health
```

Im Lab nicht wirklich auflösbar - der Check demonstriert die Vorgehensweise.
In Produktion: wenn DNS/TLS langsam ist -> Netzwerk/Provider; wenn TTFB
langsam ist -> Upstream-Service.

### Schritt 8 - Cloud-Kosten

Query 3 (`python scripts/analyze.py`):

```text
user_id    endpoint      reqs   tokens    cost_usd
user_42    /chat/slow    180    620000    9.3000
user_77    /chat         95     190000    2.8500
user_12    /chat/slow    40     160000    2.4000
```

Kosten pro Deployment-Version:

```text
version   requests   cost_usd   avg_lat   err_%
v1.4.0    2660       14.55      1571.8    2.8
v1.3.2    0          0          -         -
```

Interpretation: `user_42` verursacht auffällig hohe Kosten auf `/chat/slow`
- mögliche Ursachen: Abuse, Retry-Loop, extrem lange Prompts, fehlendes
Rate Limit.

### Schritt 9 - Skalierung

Unter Load steigt die `/chat`-Latenz parallel zu `/chat/slow`-Aufrufen,
obwohl `/chat` selbst schnell ist -> ein langsam laufender `/chat/slow`-Call
blockiert den Worker (Head-of-Line-Blocking).

Maßnahme: Worker entkoppeln, Background Queue für AI-Jobs, Autoscaling
erhöhen.

### Schritt 10 - Rollback

```text
v1.4.0 verursacht 503 Errors bei /chat/slow.
Rollback auf v1.3.2:  DEPLOYMENT_VERSION=v1.3.2 in .env, App neu starten.
Erwartung: Error Rate fällt von 6.2 % auf < 0.5 %, P95 auf < 1s.
```

---

## Findings (Zusammenfassung)

```text
Finding 1:
P95 latency for /chat/slow reached ~6.5 seconds.
Root cause: simulated AI provider delay (2-8s) plus ~18% timeout rate.

Finding 2:
Error rate for /random-error reached ~100%.
Root cause: intentional random 500/429/401/503.

Finding 3:
401 errors appear on /chat and /chat/slow when AI_API_KEY is unset.
Root cause: IAM / API-key not configured (simulated secret-manager mismatch).

Finding 4:
AI cost simulation shows higher cost per /chat/slow request than /chat.
Root cause: no rate limit and no caching; slow path uses an "expensive" model.
```

## Recommended actions

```text
- Add request timeout after 5 seconds.
- Add retry limit with exponential backoff.
- Add caching for repeated prompts.
- Add per-user rate limit.
- Add fallback model for high-latency provider responses.
- Add alert for P95 > 2 seconds on /chat/slow.
- Add alert for Error Rate > 1 % on any endpoint.
- Ensure AI_API_KEY is provisioned before deploy (secret-manager check in CI).
```

## Postmortem (Template-Kopf)

```text
Title:        /chat/slow P95 spike and 503 errors after v1.4.0
Severity:     SEV-2
Date:         2026-06-25
Authors:      [on-call]
Status:       resolved
Summary:      v1.4.0 routed /chat/slow to an expensive upstream model
              without a timeout, retry limit or rate limit. Combined with
              an unset API key this caused P95 ~6.5s, ~6% 503/401 errors
              and a ~18x cost increase. Rolled back to v1.3.2.
Impact:       Users saw 2-8s AI responses and intermittent 503/401 for ~50min.
Root cause:   Missing provider timeout + unset AI_API_KEY + no rate limit.
Action items: [link to issues]
```

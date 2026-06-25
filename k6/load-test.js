// k6 load test for the Slow AI App Incident Lab.
//
// Run with:  k6 run k6/load-test.js --vus 10 --duration 1m
// Override the target:  k6 run k6/load-test.js -e BASE_URL=http://localhost:8010
//
// The script mixes normal /chat, slow /chat/slow, /random-error and /db-query
// traffic so the resulting logs reproduce the example incident: high P95 on
// /chat/slow, elevated error rate on /random-error, and cost accumulation on
// the AI endpoints.

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:8010';
const USER = `k6_${__VU}`;

export const options = {
  scenarios: {
    chat_traffic: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '20s', target: 8 },
        { duration: '40s', target: 8 },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '5s',
      exec: 'chatScenario',
    },
    slow_chat_traffic: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '20s', target: 4 },
        { duration: '40s', target: 4 },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '5s',
      exec: 'slowChatScenario',
    },
    error_traffic: {
      executor: 'constant-vus',
      vus: 2,
      duration: '60s',
      exec: 'errorScenario',
    },
    db_traffic: {
      executor: 'constant-vus',
      vus: 2,
      duration: '60s',
      exec: 'dbScenario',
    },
  },
  thresholds: {
    // These thresholds are *expected to fail* on purpose - they document the
    // degraded SLOs the lab is designed to reproduce. Treat a red threshold
    // report as "incident reproduced", not as a test failure.
    'http_req_duration{endpoint:chat_slow}': ['p(95)<2000'],
    'http_req_failed{endpoint:random_error}': ['rate<0.05'],
  },
};

const headers = { 'Content-Type': 'application/json', 'X-User-Id': USER };

export function chatScenario() {
  const res = http.post(
    `${BASE}/chat`,
    JSON.stringify({ prompt: 'Explain P95 latency in one sentence.', user_id: USER }),
    { headers, tags: { endpoint: 'chat' } }
  );
  check(res, { 'chat status 200': (r) => r.status === 200 });
  sleep(0.5);
}

export function slowChatScenario() {
  const res = http.post(
    `${BASE}/chat/slow`,
    JSON.stringify({ prompt: 'Generate a long, detailed analysis of cloud cost spikes.', user_id: USER }),
    { headers, tags: { endpoint: 'chat_slow' }, timeout: '15s' }
  );
  // Accept 200 and 503 (provider timeout) as expected outcomes here.
  check(res, { 'slow-chat responded': (r) => [200, 503, 401].includes(r.status) });
  sleep(0.2);
}

export function errorScenario() {
  const res = http.get(`${BASE}/random-error`, { headers, tags: { endpoint: 'random_error' } });
  check(res, { 'random-error returned a status': (r) => r.status > 0 });
  sleep(0.3);
}

export function dbScenario() {
  const res = http.get(`${BASE}/db-query`, { headers, tags: { endpoint: 'db_query' } });
  check(res, { 'db-query status 200': (r) => r.status === 200 });
  sleep(0.3);
}

export function handleSummary(data) {
  // Print a compact summary focused on per-endpoint latency and error rate.
  const byTag = (data.metrics?.http_req_duration?.values?.['p(95)'] ?? 0);
  console.log(`\n=== k6 summary ===`);
  console.log(`http_req_duration p(95) overall: ${byTag} ms`);
  console.log(`http_req_failed rate overall:    ${data.metrics?.http_req_failed?.values?.rate ?? 0}`);
  console.log(`Full JSON summary available; see k6 docs to export with --out json=results.json`);
  return {};
}

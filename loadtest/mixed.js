// Steady load on the 3 services at once, with realtime listeners.
//   make loadtest-tokens n=300 && make loadtest s=mixed
// Override the size with -e VUS=400 (split 55% voters, 25% editors, 10% controllers, 10% sockets).
import { setupWorld } from './lib.js';
export { voter, editor, controller, listener } from './scenarios.js';

const VUS = Number(__ENV.VUS || 200);
const DURATION = __ENV.DURATION || '3m';

function ramped(exec, share) {
  const target = Math.max(1, Math.round(VUS * share));
  return {
    executor: 'ramping-vus',
    exec,
    startVUs: 0,
    stages: [
      { duration: '30s', target },
      { duration: DURATION, target },
      { duration: '15s', target: 0 },
    ],
    gracefulRampDown: '5s',
  };
}

export const options = {
  setupTimeout: '5m',
  scenarios: {
    voters: ramped('voter', 0.55),
    editors: ramped('editor', 0.25),
    controllers: ramped('controller', 0.1),
    listeners: ramped('listener', 0.1),
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    'http_req_duration{scenario:voters}': ['p(95)<300'],
  },
};

export function setup() {
  return setupWorld();
}

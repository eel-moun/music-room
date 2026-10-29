// Find the breaking point: arrival rate climbs until latency or errors give way.
//   make loadtest-tokens n=500 && make loadtest s=stress
// Each iteration is one request; the stop conditions below abort the test when it breaks.
import { setupWorld } from './lib.js';
import { controller, editor, voter } from './scenarios.js';

const PEAK = Number(__ENV.PEAK || 3000); // iterations per second at the end

export const options = {
  setupTimeout: '5m',
  scenarios: {
    climb: {
      executor: 'ramping-arrival-rate',
      startRate: 50,
      timeUnit: '1s',
      preAllocatedVUs: 500,
      maxVUs: 3000,
      stages: [
        { duration: '1m', target: Math.round(PEAK * 0.25) },
        { duration: '1m', target: Math.round(PEAK * 0.5) },
        { duration: '1m', target: Math.round(PEAK * 0.75) },
        { duration: '1m', target: PEAK },
      ],
    },
  },
  thresholds: {
    // abortOnFail: stop as soon as the service is clearly saturated.
    http_req_failed: [{ threshold: 'rate<0.05', abortOnFail: true, delayAbortEval: '20s' }],
    http_req_duration: [{ threshold: 'p(95)<2000', abortOnFail: true, delayAbortEval: '20s' }],
  },
};

export function setup() {
  return setupWorld();
}

// Same mix as mixed.js, without think time: each iteration is pure load.
export default function (world) {
  const roll = Math.random();
  if (roll < 0.65) voter(world, true);
  else if (roll < 0.9) editor(world, true);
  else controller(world, true);
}

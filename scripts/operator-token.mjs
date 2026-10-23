import { readFileSync } from 'node:fs';
// Explicit local-terminal command only. Never called by the frontend or server logs.
if (!process.stdout.isTTY) {
  console.error('Run this command directly in your private terminal to view the operator key.');
  process.exit(1);
}
try {
  const token = readFileSync(new URL('../backend/data/operator-token', import.meta.url), 'utf8').trim();
  console.log('Local Recognition & World Quality operator key (keep private):');
  console.log(token);
} catch {
  console.error('Start npm run dev once to create the local operator key, then retry.');
  process.exit(1);
}

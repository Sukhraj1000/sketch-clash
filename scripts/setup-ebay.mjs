import { chmod, lstat, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { createInterface } from 'node:readline/promises';
import { Writable } from 'node:stream';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));

export async function saveEbayCredentials(clientId, clientSecret, directory = projectRoot) {
  const values = [clientId.trim(), clientSecret.trim()];
  if (values.some(key => key.length < 8 || key.length > 4096 || !/^[A-Za-z0-9_.:\/+=-]+$/.test(key))) {
    throw new Error('Paste the API key only, without quotes, spaces, or extra lines.');
  }
  const path = join(directory, '.env.local');
  let previous = '';
  try {
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink()) throw new Error('The local environment path must be a regular file.');
    previous = await readFile(path, 'utf8');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  // Keep other local settings. The key is never passed in process arguments or logs.
  const retained = previous.split(/\r?\n/).filter(line => !/^\s*(?:export\s+)?(?:EBAY_CLIENT_ID|EBAY_CLIENT_SECRET)\s*=/.test(line)).join('\n').trimEnd();
  const temporary = join(directory, `.env.${randomUUID()}.tmp`);
  try {
    await writeFile(temporary, `${retained ? retained + '\n' : ''}EBAY_CLIENT_ID=${values[0]}\nEBAY_CLIENT_SECRET=${values[1]}\n`, { mode: 0o600, flag: 'wx' });
    await chmod(temporary, 0o600);
    await rename(temporary, path);
  } finally {
    await unlink(temporary).catch(error => { if (error.code !== 'ENOENT') throw error; });
  }
}

async function main() {
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    throw new Error('Run npm run setup:ebay in your local terminal. Do not pass the key as an argument.');
  }
  if (process.argv.length !== 2) throw new Error('Do not pass the key as an argument. Use the hidden prompt.');
  // Discard readline's echo and terminal redraws, including pasted characters.
  const mutedOutput = new Writable({ write(_chunk, _encoding, done) { done(); } });
  const prompt = createInterface({ input: process.stdin, output: mutedOutput, terminal: true, historySize: 0 });
  prompt.once('SIGINT', () => {
    prompt.close();
    process.stdout.write('\nCancelled. Nothing saved.\n');
    process.exitCode = 130;
  });
  process.stdout.write('Enter production eBay Client ID (App ID; input is hidden), then press Enter: ');
  let clientId, clientSecret;
  try {
    clientId = await prompt.question('');
    process.stdout.write('\nEnter production eBay Client Secret (Cert ID; input is hidden), then press Enter: ');
    clientSecret = await prompt.question('');
  } finally {
    prompt.close();
    process.stdout.write('\n');
  }
  if (process.exitCode === 130) return;
  await saveEbayCredentials(clientId, clientSecret);
  clientId = clientSecret = undefined;
  process.stdout.write('Saved locally to .env.local with owner-only read/write permissions. Other settings preserved. Restart npm run dev to enable eBay lookups; no request was sent.\n');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => {
    if (process.exitCode === 130) return;
    // Never print exception objects: filesystem or parser errors could contain private input.
    process.stderr.write('Credentials were not saved. Run this command in a local terminal and enter the eBay production credentials.\n');
    process.exitCode = 1;
  });
}

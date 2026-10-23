import { chmod, lstat, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { createInterface } from 'node:readline/promises';
import { Writable } from 'node:stream';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));
// Non-secret connection details supplied by the owner of this local project.
const cluster = 'cluster0.hgrpk3.mongodb.net';
const username = 'sketch_clash_app';
const database = 'sketch_clash';

function encodeCredential(value) {
  return encodeURIComponent(value).replace(/[!'()*]/g, character => `%${character.charCodeAt(0).toString(16).toUpperCase()}`);
}

export async function saveMongoPassword(password, directory = projectRoot) {
  // Whitespace can be part of a password. Never trim or print it.
  if (typeof password !== 'string' || !password.length || password.length > 4096 || /[\x00-\x1f\x7f]/.test(password)) {
    throw new Error('Enter a non-empty database password without control characters.');
  }
  const uri = `mongodb+srv://${encodeCredential(username)}:${encodeCredential(password)}@${cluster}/?retryWrites=true&w=majority&appName=SketchClash`;
  const path = join(directory, '.env.local');
  let previous = '';
  try {
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink()) throw new Error('The environment path must be a regular file.');
    previous = await readFile(path, 'utf8');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const retained = previous.split(/\r?\n/).filter(line => !/^\s*(?:export\s+)?(?:MONGODB_URI|MONGODB_DATABASE|SKETCH_REPOSITORY)\s*=/.test(line)).join('\n').trimEnd();
  const temporary = join(directory, `.env.${randomUUID()}.tmp`);
  try {
    await writeFile(temporary, `${retained ? retained + '\n' : ''}MONGODB_URI=${uri}\nMONGODB_DATABASE=${database}\nSKETCH_REPOSITORY=mongodb\n`, { mode: 0o600, flag: 'wx' });
    await chmod(temporary, 0o600);
    await rename(temporary, path);
  } finally {
    await unlink(temporary).catch(error => { if (error.code !== 'ENOENT') throw error; });
  }
}

async function main() {
  if (!process.stdin.isTTY || !process.stdout.isTTY || process.argv.length !== 2) {
    throw new Error('Run npm run setup:mongodb in a local terminal with no password argument.');
  }
  process.stdout.write(`Atlas cluster: ${cluster}\nDatabase user: ${username}\n`);
  const mutedOutput = new Writable({ write(_chunk, _encoding, done) { done(); } });
  const prompt = createInterface({ input: process.stdin, output: mutedOutput, terminal: true, historySize: 0 });
  prompt.once('SIGINT', () => {
    prompt.close();
    process.stdout.write('\nCancelled. Nothing saved.\n');
    process.exitCode = 130;
  });
  process.stdout.write('Enter this database user’s password (input is hidden), then press Enter: ');
  let password;
  try {
    password = await prompt.question('');
  } finally {
    prompt.close();
    process.stdout.write('\n');
  }
  if (process.exitCode === 130) return;
  await saveMongoPassword(password);
  password = undefined;
  process.stdout.write('Saved Atlas settings in .env.local with owner-only permissions. Other settings, including Gemini, were preserved.\nNo connection test has run yet. Restart using npm run dev to activate MongoDB mode.\n');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => {
    if (process.exitCode === 130) return;
    // Parser/filesystem errors may contain private input; never print exception objects.
    process.stderr.write('Settings were not saved. Run npm run setup:mongodb in a terminal with no arguments and enter the database password at the hidden prompt.\n');
    process.exitCode = 1;
  });
}

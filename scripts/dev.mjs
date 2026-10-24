import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
const python=process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python';
if(!existsSync(python)){console.error('Create the backend environment first: uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r backend/requirements.lock.txt');process.exit(1);}
const memory=process.argv.includes('--demo');
const offline=process.argv.includes('--offline');
if(offline)console.log('AI PAUSED — Gemini requests are disabled. Local island work and Atlas persistence remain available.');
if(memory)console.log('DEVELOPMENT MEMORY MODE — records disappear when this server restarts. Real recognition; no durable MongoDB unlocks.');
const env={...process.env,...(memory?{SKETCH_REPOSITORY:'memory'}:{}),...(offline?{SKETCH_AI_PAUSED:'true'}:{})};
const children=[spawn(python,['-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000'],{stdio:'inherit',env}),spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173','--strictPort'],{stdio:'inherit',env:process.env})];
let stopping=false;
function stop(code=0){if(stopping)return;stopping=true;for(const child of children)child.kill('SIGTERM');process.exitCode=code;}
for(const child of children){child.on('error',error=>{console.error(error.message);stop(1)});child.on('exit',code=>stop(code??0));}
process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());

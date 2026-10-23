import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({plugins:[react(),tailwindcss()],base:'./',optimizeDeps:{include:['three','@react-three/fiber','@react-three/drei']},server:{host:'127.0.0.1',port:5173,strictPort:true,watch:{ignored:['**/.venv/**','**/backend/**','**/work/**']},proxy:{'/api':'http://127.0.0.1:8000'}},preview:{host:'127.0.0.1',proxy:{'/api':'http://127.0.0.1:8000'}}});

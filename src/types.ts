export type Phase = 'HOME' | 'THEME' | 'DRAW_P1' | 'DRAW_P2' | 'REVEAL' | 'BATTLE' | 'RESULTS';
export type Fighter = { id:string; name:string; image:string; subtitle:string; side:0|1; color:string; kind?:'photo'; archetype?:string };

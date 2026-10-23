# Sketch Clash

A cinematic, frontend-only sketchbook fighting game. Two players draw on one device, their original sketches lift off the page, and a scripted arcade showdown ends in a dramatic KO.

Built with React, TypeScript, Vite, Tailwind CSS, Motion for React, and Canvas. Fonts and original SVG artwork are bundled locally.

## Run locally

Use **Node.js 22.18 or newer** and npm. From this directory:

```sh
npm ci
npm run dev
```

Open the local URL printed by Vite. The development server binds to `127.0.0.1`.

For a production build and local preview:

```sh
npm run build
npm run preview
```

The build runs TypeScript checks and creates `dist/`. Serve that directory with a static web server; opening `index.html` directly from disk is not the supported launch method.

Run `npm run test:combat` to verify the complete combat timeline, damage, contact freezes, hit flashes, replay reset, and reduced-motion transforms.

## Play and demo controls

- **LET’S PLAY** starts the theme reveal, which always selects **Animals** in this prototype.
- **QUICK DRAW** switches between 60 and 20 seconds per player.
- Each player selects **I’M READY** to start their own timer. Player 2 receives a fresh, hidden page; pass the device and look away.
- Draw with a mouse, pen, or touch. The toolbar provides a pen, eraser, four colours, brush size, undo, and clear.
- **LOCK IN MY FIGHTER** submits the original sketch. The timer stops editing when it expires; a nonempty sketch can still be submitted. A blank page cannot be submitted.
- **WATCH THE SHOWDOWN** skips drawing and runs the reveal and battle with Scratch and Chomps, the two preset fighters.
- **RUN IT BACK** replays the battle with the same fighters. **PLAY AGAIN**, the logo, or **EXIT ROUND** returns to the lobby and resets the round.

## Prototype behaviour

All game state lives in browser memory. Drawings are exported as cropped, transparent images and used directly for the fighter sprites; no generated art replaces them. Refreshing or leaving the page discards the current round.

The fight follows a fixed **12.8-second** timeline. **Player 1 always wins**, whether using preset fighters or original drawings. Names, attributes, damage, and results are fixtures; the drawing does not determine combat strength.

There is no backend, database, AI recognition, theme validation, market lookup, authentication, or networked multiplayer. Two-player mode is a shared-device handoff. No API keys or service accounts are required. Once dependencies are installed, the app makes no external service requests during play.

## Source map

| Path | Responsibility |
| --- | --- |
| `src/App.tsx` | Screen flow, landing, theme, fighter reveal, and victory |
| `src/components/SketchCanvas.tsx` | Drawing tools, pointer input, timer, and transparent image export |
| `src/components/BattleArena.tsx` | Fighter sprites, health bars, impacts, and battle presentation |
| `src/game/director.ts` | Cancellable animation clock with cleanup on exit and replay |
| `src/game/battle.ts` | Deterministic hit sequence, health, poses, and camera movement |
| `src/game/fixtures.ts` | Preset fighter profiles |
| `src/types.ts` | Shared game types |
| `src/styles.css` | Paper-and-ink visual system and responsive layouts |
| `public/art/` | Original transparent fighter and crown SVGs |

The screen flow is `HOME → THEME → DRAW_P1 → DRAW_P2 → REVEAL → BATTLE → RESULTS`.

## Reduced motion

The app follows the operating system or browser’s `prefers-reduced-motion` setting. It reduces fighter travel and ambient movement and disables camera shake, hit flashes, and battle particles. Health changes, the scripted timeline, and the winner remain the same. Desktop is the primary presentation target; the drawing interface also supports smaller screens.

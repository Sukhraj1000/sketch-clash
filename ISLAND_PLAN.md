# Sketch Clash — an island worth collecting for

Implemented locally on 24 October 2026. Verification and operating limits are recorded in HANDOVER.md.

## Direction

Restore the original paper arcade identity: huge Sketch Clash lettering, expressive illustrated opponents, coral/mint/yellow, heavy ink borders, taped cards and confident motion. Keep the working camera, feedback and creator tools. Replace the quiet display shelf with a playable island where objects contribute because of what they are.

## The playable loop

1. Capture an object and complete a battle; both participants keep joining the island under the existing rules.
2. Start the settlement. Existing residents get object-based capabilities and a persistent worker state.
3. Choose a community project. Agents notice missing resources, travel to work sites, gather supplies and contribute construction work.
4. Watch a garden, workshop, beacon and boardwalk appear in stages. Each has three levels. Buildings improve the economy; residents earn experience, develop roles and remember completed work. Once construction is complete, expeditions consume supplies and add discoveries.
5. Give a resident a job or return it to autonomy. Switch priorities, inspect its plan/history, pause the settlement, or ask for a fresh bounded AI plan.
6. New object types add useful capabilities. Repeated battles preserve the original resident rather than duplicating it or changing combat balance.

The first building should be achievable during a short demo, with later upgrades sustaining progression. The interface must show what is happening, why each object is useful and what the next completion earns.

## Runtime and cost

MongoDB Atlas stores state; it does not run the agents. One local Python scheduler advances the colony even when the browser closes, while the home Mac and backend remain running. Transactions and action IDs protect rewards from duplicate ticks, refreshes and restarts. A bounded catch-up window handles downtime honestly; it is not an unlimited offline reward generator.

Movement and routine decisions use inexpensive deterministic simulation. A separate, optional Gemini Flash-Lite planner supplies persistent personas and chooses from each resident's allowed actions based on real recent outcomes. Its outputs cannot invent resources, alter combat, execute code or modify saved appearances. Initial persona creation and occasional reflection use bounded batches: at most six residents per request, one automatic request every 15 minutes, at most 12 requests and 84,000 reserved tokens per UTC day. Each call has a context/output limit and an explicit timeout. Unknown provider outcomes are recorded and never automatically repeated. No precise monetary-cost claim is made.

Seeded object roles work without model access, with their origin shown honestly. AI planning changes a preference within permitted useful actions; player assignments take precedence. Event memories describe actual simulated outcomes, not invented real-world activity.

## Persistence boundary

New island simulation, agent, command, event and reasoning records are separate from battles, resident appearances, media and quality datasets. Their state is world-scoped. Initialization is an explicit action; reading the island does not silently spend model credits. Starting the settlement enables bounded periodic reasoning, with an independent control to turn it off. Pausing simulation also stops new reasoning work.

## Delivery order

- Restore the original visual direction and preserve all existing gameplay functions.
- Implement and test the autonomous resource/building loop and durable commands.
- Render authoritative tasks as walking, carrying, watering, planning and construction; add clickable projects and resident inspection.
- Connect bounded persona/reflection calls and persistent memories.
- Verify production build, existing combat/image/backend tests, isolated simulation concurrency/restart, live Gemini/Atlas integration, actual browser interactions and mobile layout.
- Make focused commits, push to the existing private remote and leave a runnable local app with an honest handover.

## What this increment does not claim

This is a simulated colony of object-inspired agents, not physical robotics or sentient objects. MongoDB persistence is separate from model training. There is no monetary yield, blockchain economy, arbitrary generated executable code, public hosting or cloud agent process running while the home backend is stopped.

## Demo the implemented loop

1. Show the restored arcade home and an everyday object. Explain: “It fights once, then becomes a useful resident.”
2. Show a real capture/review or clearly identify a saved proposal. Keep the source image visible and distinguish actual recognition from the scripted Showdown.
3. Finish or replay a real battle, identifying a replay honestly. Open the island and select the object: role, capabilities, current job, XP and recorded memories make its purpose visible.
4. Change a building priority or assign a useful job. Follow the resident to its work site. Show a genuinely built stage and the production benefit; do not call saved progress a fresh instant achievement.
5. Reload to show persistence. Explain that Atlas stores durable agents/tasks/history and the local worker executes their simulation. Show the bounded AI counter and toggle; no model is called per movement frame.

The implementation and live/test evidence are recorded in HANDOVER.md. This is an operating prototype, with limited procedural structures and validated object-family actions, not an open-ended physical-world learning system.

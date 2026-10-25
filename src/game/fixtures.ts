import type { Fighter } from '../types';

export const PRESET_FIGHTERS: [Fighter, Fighter] = [
  {
    id: 'graphite',
    name: 'GRAPHITE',
    subtitle: 'THE PLAN MAKER',
    image: '/art/graphite.svg',
    side: 0,
    color: '#FF596E',
    characterVisual: {
      display_name: 'GRAPHITE', object_type: 'pencil', canonical_type_id: 'pencil', image_ref: '/art/graphite.svg',
      visual_spec: { template_id: 'generic', palette: ['#FFD166', '#FF596E'], scale: 1, proportions: { width: 1, height: 1 }, accessories: ['eyes', 'arms', 'feet'], animation_style: 'bouncy', schema_version: 'authored-demo-1', appearance_seed: 17 },
    },
  },
  {
    id: 'kiln',
    name: 'KILN',
    subtitle: 'BUILT TO CARRY THE CREW',
    image: '/art/kiln.svg',
    side: 1,
    color: '#66E0D4',
    characterVisual: {
      display_name: 'KILN', object_type: 'mug', canonical_type_id: 'mug', image_ref: '/art/kiln.svg',
      visual_spec: { template_id: 'mug', palette: ['#66E0D4', '#FFD166'], scale: 1, proportions: { width: 1, height: 1 }, accessories: ['eyes', 'arms', 'feet', 'handle'], animation_style: 'wobbly', schema_version: 'authored-demo-1', appearance_seed: 29 },
    },
  },
];

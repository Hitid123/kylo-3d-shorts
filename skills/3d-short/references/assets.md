# Assets and licences

Rule of thumb: if a real model of the thing exists under a safe licence, import it; build it procedurally only when nothing fits. Always keep a list of what you imported in the project folder (`assets_used.txt`) with source and licence.

| Source | How | Licence | Use for |
|---|---|---|---|
| Procedural (s3d) | `s3d.box/cylinder/...` | yours | structure, walls, slabs, pipes, water |
| Poly Haven | `assets.search("ladder")`, `assets.model(id, size, loc)`, `assets.texture_on(obj, id)`, `assets.hdri(id)` | CC0 — any use, no credit | ladders, barrels, furniture, rocks, plants, PBR textures (mud, concrete, planks), HDRI skies |
| Poly Pizza (via Blender MCP `search_assets`) | MCP | CC0 or CC-BY (credit the author in the description) | stylised props |
| Sketchfab (via Blender MCP) | MCP | per model: only CC0 / CC-BY (credit) / bought Standard licence for monetized videos; **never** CC BY-NC or Editorial | specific realistic objects |
| AI 3D generators (Blender MCP `generate_3d`: Meshy, Tripo, Hunyuan3D, Rodin) | MCP | check each provider's plan terms; Meshy free = CC BY 4.0; Hunyuan3D community licence excludes EU/UK/South Korea | one-off hero objects nothing else has |

Notes
- Size imports explicitly (`size=` in metres: ladder 2.5–3, barrel 1, door 2.1, car 4.5) and sit them on their surface.
- Prefer 1k textures; 2k only for close-ups.
- No brand logos, no real people, no copyrighted characters in the scene.
- ElevenLabs (voice, sound effects, music via `scripts/eleven.py`): the free plan is non-commercial and has no music; use a paid plan for a monetized channel and keep the plan active when you generate. Check ElevenLabs' current terms before publishing.
- Music: ElevenLabs instrumental or tracks the user owns / licensed for YouTube. Never upload a song you don't have rights to: a Content ID claim blocks a Short longer than 1 minute worldwide.
- Textures used by default (all Poly Haven CC0): brown_mud_02, dry_ground_rocks, red_mud_stones, rocks_ground_02, rock_surface, leafy_grass, weathered_brown_planks, painted_plaster_wall, clay_roof_tiles, corrugated_iron_02, plank_flooring, fine_grained_wood; HDRI kloofendal_48d_partly_cloudy_puresky; model shrub_02.

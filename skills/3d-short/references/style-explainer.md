# The look (realistic "what if" explainers)

What the ZackD-style explainers do on screen (two shorts sampled frame by frame, Nov 2026: "What If Humans Had Hummingbird Hearts", "How Horseflies Bite You") and how `examples/whatif` reproduces it. Use this instead of `style.md` when the short follows a person or goes inside the body.

## Frame and shots
- A realistic person (`mh.Person`, see `characters.md`) in close-ups and medium close-ups: 70–85 mm, f/2.8, the background melts into colour. Face fills a third of the frame in emotional beats.
- Bright daylight, saturated clothes (one strong colour tee), blue sky / green yard behind. View transform AgX with the **Punchy** look.
- Hard cuts every 2–5 s. Each shot is one clear action on the word that names it, with a slow push-in (8–15 % of the distance). One small camera shake on an impact ("pop").
- Inside views (X-ray): the same person duplicated as glass — blue fresnel skin (`XrayGlass` material: emission on the rim, transparent in the middle), dark navy void, wet red organs, white bones, glowing particles for air/blood/signals. Shoot anatomy in profile so the shape reads.
- Real-case beats: a short ward/room scene with clean props (bed, drip stand, monitor) — not more than one shot.

## Acting
- Faces carry these shorts: `face(frame, "pre_sneeze" | "squeeze" | "shock" | "pain" | "worried" | "relief" | "puff" | "sleep")`.
- Hands touch the body where the story is: `pose(frame, "pinch_nose" | "cover_mouth" | "grab_throat" | "elbow_sneeze" | "point" | "fist_press" | "interlace" | "hands_up")` — solved on the real nose/throat/chest of this body; anything else with `act()`.
- Small reactions between big poses: `jolt()` for a held sneeze, a cough, a hit.

## Captions
- `assemble.py --style explainer`: white sentence-case words with a black outline, small, low in the frame (~80 % height), up to 4 words per chunk.

## Sound
- Voice dominant, a sound on every physical moment (squeeze, pop, tear, bubbles, monitor beep), a low tense music bed. Same loudness targets as `style.md`.

## Preview checklist
1. Hands touch what they should (nose, throat) — no fingers through the face.
2. Mouth/eyes read at phone size; expressions change on the words.
3. X-ray: organs saturated red, not washed pink; nothing outside the glass body; particles visible.
4. Every cut changes the picture clearly (real ↔ inside ↔ another angle).
5. No logos on clothes (mh.py recolours the tee for this reason).

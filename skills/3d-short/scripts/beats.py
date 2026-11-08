"""Map script beats onto the voiceover timeline.

  python beats.py script.txt words.json beats.json [--fps 30]

script.txt: one beat per line (blank lines ignored). A beat is one visual step:
  "If you dig a hole in your backyard and pour concrete, you have a pool."
  "But the water turns green in a week."
  "So you add a pump and a filter. This is a filter."
beats.json: [{"i": 0, "text": ..., "s": 0.12, "e": 3.9, "fs": 4, "fe": 117, "words": [{"w","s","e"}...]}, ...]
The Blender build script reads it, so every object lands on the word that names it.
"""
import difflib
import json
import re
import sys


def norm(w):
    return re.sub(r"[^\w]", "", w.lower())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fps = int(sys.argv[sys.argv.index("--fps") + 1]) if "--fps" in sys.argv else 30
    script, words_path, out = args[:3]
    beats = [l.strip() for l in open(script) if l.strip()]
    words = json.load(open(words_path))
    toks, owner = [], []
    for i, b in enumerate(beats):
        for t in b.split():
            if norm(t):
                toks.append(norm(t))
                owner.append(i)
    heard = [norm(w["w"]) for w in words]
    sm = difflib.SequenceMatcher(a=toks, b=heard, autojunk=False)
    tok2word = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            tok2word[blk.a + k] = blk.b + k
    res = []
    for i, text in enumerate(beats):
        idx = [tok2word[t] for t in range(len(toks)) if owner[t] == i and t in tok2word]
        if idx:
            res.append({"i": i, "text": text, "w0": min(idx), "w1": max(idx)})
        else:
            res.append({"i": i, "text": text, "w0": None, "w1": None})
    # fill gaps for beats whose words weren't recognised
    for k, r in enumerate(res):
        if r["w0"] is None:
            prev = next((x["w1"] for x in reversed(res[:k]) if x["w1"] is not None), -1)
            r["w0"] = r["w1"] = min(prev + 1, len(words) - 1)
    for k, r in enumerate(res):
        s = words[r["w0"]]["s"]
        e = words[res[k + 1]["w0"]]["s"] if k + 1 < len(res) else words[-1]["e"] + 0.6
        r.update({"s": round(s, 3), "e": round(e, 3), "fs": int(round(s * fps)) + 1, "fe": int(round(e * fps)) + 1,
                  "words": words[r["w0"]: r["w1"] + 1]})
        del r["w0"], r["w1"]
    json.dump(res, open(out, "w"), indent=1, ensure_ascii=False)
    for r in res:
        print(f'{r["i"]:2d}  {r["s"]:6.2f}–{r["e"]:6.2f}s  {r["text"][:70]}')


if __name__ == "__main__":
    main()

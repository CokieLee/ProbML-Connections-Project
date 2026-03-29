#!/usr/bin/env python3

# Purple Connections Generator — Clean Edition
#
# pip install pronouncing
# python purple_gen.py
# python purple_gen.py --seed 42 --count 3

import json, os, random, subprocess, argparse
from collections import defaultdict
from itertools import combinations
import pronouncing

REPO_URL = "https://github.com/Eyefyre/NYT-Connections-Answers.git"
REPO_DIR = "NYT-Connections-Answers"
DATA_FILE = os.path.join(REPO_DIR, "connections.json")

VOWELS = set("aeiou")
LEFT_HAND = set("qwertasdfgzxcvb")
RIGHT_HAND = set("yuiophjklnm")
NUMBERS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


# ---- loading ----

def sync_repo():
    if os.path.isdir(REPO_DIR):
        subprocess.run(["git", "-C", REPO_DIR, "pull", "--ff-only"], capture_output=True)
    else:
        if subprocess.run(["git", "clone", REPO_URL, "--depth", "1"], capture_output=True).returncode != 0:
            return False
    return True

def load_words(path):
    return {line.strip().lower() for line in open(path) if line.strip()}

def load_past():
    past = set()
    for puzzle in json.load(open(DATA_FILE)):
        for answer in puzzle["answers"]:
            if answer["level"] >= 0:
                past.add(tuple(sorted(m.upper() for m in answer["members"])))
    return past

def is_dupe(words, past):
    return tuple(sorted(w.upper() for w in words)) in past

def build_pron():
    pronouncing.init_cmu()
    w2p, p2w = defaultdict(list), defaultdict(list)
    for word, pron in pronouncing.pronunciations:
        w = word.lower().strip("()")
        if w.isalpha():
            w2p[w].append(pron)
            p2w[pron].append(w)
    return w2p, p2w


# ---- string helpers ----
# these replace a LOT of manual loops and conditionals throughout the generators

def get_vowels(word):
    """Pull just the vowels from a word: 'banana' → ['a','a','a']"""
    return [c for c in word if c in VOWELS]

def has_all_same_vowel(word):
    """Do all vowels in this word match? 'drama' → True, 'ocean' → False"""
    v = get_vowels(word)
    return len(v) >= 2 and len(set(v)) == 1

def is_alternating(word):
    """Does every letter alternate between vowel and consonant?"""
    return len(word) >= 5 and all(
        (word[i] in VOWELS) != (word[i+1] in VOWELS)
        for i in range(len(word) - 1)
    )

def count_double_pairs(word):
    """How many consecutive same-letter pairs? 'coffee' → 2 (ff, ee)"""
    return sum(word[i] == word[i+1] for i in range(len(word) - 1))

def typed_with(word, keys):
    """Can this word be typed using only the given set of keys?"""
    return len(word) >= 4 and all(c in keys for c in word)

def contains_sub(word, sub):
    """Does this word contain the substring (and isn't just the substring)?"""
    return sub in word and word != sub and len(word) >= len(sub) + 1

def rhyme_key(pron):
    """Extract the rhyming part of a pronunciation: last stressed vowel onward."""
    phones = pron.split()
    for i in range(len(phones) - 1, -1, -1):
        if any(c.isdigit() for c in phones[i]):
            return " ".join(phones[i:])
    return pron

def get_rhyme(word, w2p):
    """Get the rhyme key for a word, or None if not in the pronunciation dict."""
    prons = w2p.get(word, [])
    return rhyme_key(prons[0]) if prons else None


# ---- pick helper ----
# most generators follow the same pattern: group words by some property,
# filter to groups of 4+, pick one group, grab 4 random words, dupe check.
# this helper does that whole flow.

def pick_from_groups(groups, past, count):
    """
    Given a dict of {key: [words]}, find groups with 4+ words,
    pick `count` of them, grab 4 words from each, dupe check.
    Returns list of (key, [4 words]) tuples.
    """
    good = {k: v for k, v in groups.items() if len(v) >= 4}
    keys = list(good.keys())
    random.shuffle(keys)

    results = []
    for key in keys:
        if len(results) >= count:
            break
        picked = random.sample(good[key], 4)
        if not is_dupe(picked, past):
            results.append((key, picked))
    return results


# ================================================================
# TIER 1: META WORD PROPERTIES
# ================================================================

def gen_same_vowel(common, past, count):
    groups = defaultdict(list)
    for w in common:
        if has_all_same_vowel(w) and len(w) >= 5:
            groups[get_vowels(w)[0]].append(w)

    return [
        {"group": f"EVERY VOWEL IS \"{v.upper()}\"",
         "members": [w.upper() for w in words],
         "explanation": f"All vowels in each word are {v.upper()}",
         "type": "meta_same_vowel"}
        for v, words in pick_from_groups(groups, past, count)
    ]


def gen_keyboard(common, past, count):
    results = []
    for hand, keys, label in [("left", LEFT_HAND, "LEFT"), ("right", RIGHT_HAND, "RIGHT")]:
        if len(results) >= count:
            break
        candidates = sorted(
            [w for w in common if typed_with(w, keys)],
            key=lambda w: -len(w)  # prefer longer words — harder to spot
        )
        pool = candidates[:max(4, len(candidates) // 2)]
        if len(pool) >= 4:
            picked = random.sample(pool, 4)
            if not is_dupe(picked, past):
                results.append({
                    "group": f"TYPED WITH {label} HAND ONLY",
                    "members": [w.upper() for w in picked],
                    "explanation": f"All letters on {hand} side of QWERTY",
                    "type": f"meta_keyboard_{hand}"})
    return results


def gen_contains_number(common, past, count):
    groups = {num: [w for w in common if contains_sub(w, num)] for num in NUMBERS}
    return [
        {"group": f"CONTAINS \"{num.upper()}\"",
         "members": [w.upper() for w in words],
         "explanation": ", ".join(f"{w.upper()} hides {num.upper()}" for w in words),
         "type": "meta_number"}
        for num, words in pick_from_groups(groups, past, count)
    ]


def gen_s_front(common, past, count):
    # words where adding S to the front makes a different word
    candidates = [(w, f"s{w}") for w in common
                  if len(w) >= 3 and f"s{w}" in common and not w.startswith("s")]
    if len(candidates) < 4:
        return []

    random.shuffle(candidates)
    picked = candidates[:4]
    words = [w for w, _ in picked]
    if is_dupe(words, past):
        return []

    return [{"group": "ADD \"S\" TO THE FRONT = NEW WORD",
             "members": [w.upper() for w in words],
             "explanation": ", ".join(f"S+{w.upper()} = {sw.upper()}" for w, sw in picked),
             "type": "meta_s_front"}]


def gen_swap_ends(common, past, count):
    # swap first and last letter → different word
    pairs = []
    seen = set()
    for w in common:
        if len(w) < 4: continue
        swapped = f"{w[-1]}{w[1:-1]}{w[0]}"
        if swapped in common and swapped != w:
            key = tuple(sorted([w, swapped]))
            if key not in seen:
                seen.add(key)
                pairs.append((w, swapped))

    if len(pairs) < 4:
        return []
    random.shuffle(pairs)
    picked = pairs[:4]
    words = [a for a, _ in picked]
    if is_dupe(words, past):
        return []

    return [{"group": "SWAP FIRST AND LAST LETTER = NEW WORD",
             "members": [w.upper() for w in words],
             "explanation": ", ".join(f"{a.upper()} ↔ {b.upper()}" for a, b in picked),
             "type": "meta_swap_ends"}]


def gen_doubles(common, past, count):
    candidates = [w for w in common if count_double_pairs(w) >= 2 and len(w) >= 5]
    if len(candidates) < 4:
        return []
    random.shuffle(candidates)
    picked = candidates[:4]
    if is_dupe(picked, past):
        return []

    return [{"group": "TWO SETS OF DOUBLE LETTERS",
             "members": [w.upper() for w in picked],
             "explanation": ", ".join(w.upper() for w in picked) + " — each has 2+ double-letter pairs",
             "type": "meta_doubles"}]


def gen_alternating(common, past, count):
    candidates = [w for w in common if is_alternating(w)]
    if len(candidates) < 4:
        return []
    random.shuffle(candidates)
    picked = candidates[:4]
    if is_dupe(picked, past):
        return []

    return [{"group": "ALTERNATING VOWELS AND CONSONANTS",
             "members": [w.upper() for w in picked],
             "explanation": "Every letter alternates V/C perfectly",
             "type": "meta_alternating"}]


def gen_secret_split(common, past, count):
    # word = two smaller words glued together
    splits = []
    for w in common:
        if len(w) < 6: continue
        for i in range(3, len(w) - 2):
            left, right = w[:i], w[i:]
            if left in common and right in common:
                splits.append((w, left, right))
                break

    if len(splits) < 4:
        return []
    random.shuffle(splits)
    picked = splits[:4]
    words = [s[0] for s in picked]
    if is_dupe(words, past):
        return []

    return [{"group": "SECRETLY TWO WORDS",
             "members": [w.upper() for w in words],
             "explanation": ", ".join(f"{w.upper()} = {l.upper()}+{r.upper()}" for w, l, r in picked),
             "type": "meta_split"}]


def gen_chop_first(common, past, count):
    # remove first letter → new word
    candidates = [(w, w[1:]) for w in common if len(w) >= 4 and w[1:] in common]
    if len(candidates) < 4:
        return []
    random.shuffle(candidates)
    picked = candidates[:4]
    words = [w for w, _ in picked]
    if is_dupe(words, past):
        return []

    return [{"group": "REMOVE FIRST LETTER = NEW WORD",
             "members": [w.upper() for w in words],
             "explanation": ", ".join(f"{w.upper()} → {r.upper()}" for w, r in picked),
             "type": "meta_chop_first"}]


# ================================================================
# TIER 2: TWO-LAYER HIDDEN PATTERNS
# ================================================================

def build_hiding(common, mode):
    """Build a map of short_word → [long_words] for a given hiding mode."""
    groups = defaultdict(list)
    for short in (w for w in common if 3 <= len(w) <= 5):
        for long in common:
            if long == short or len(long) < len(short) + 2:
                continue
            if mode == "start" and long.startswith(short):
                groups[short].append(long)
            elif mode == "end" and long.endswith(short):
                groups[short].append(long)
            elif mode == "inside":
                pos = long.find(short)
                if pos > 0 and pos + len(short) < len(long):
                    groups[short].append(long)
    return {k: v for k, v in groups.items() if v}


def gen_hidden_rhyme(hiding, past, w2p, count, mode):
    """4 words each hiding a DIFFERENT short word — those hidden words all rhyme."""
    # group the hidden words by rhyme
    by_rhyme = defaultdict(list)
    for short in hiding:
        rk = get_rhyme(short, w2p)
        if rk and len(rk.split()) >= 2:
            by_rhyme[rk].append(short)

    good = {k: v for k, v in by_rhyme.items() if len(v) >= 4}
    keys = list(good.keys())
    random.shuffle(keys)

    results = []
    for rk in keys:
        if len(results) >= count:
            break
        shorts = list(good[rk])
        random.shuffle(shorts)

        # pick 4 different hidden words, each with a different answer word
        picked, used_words = [], set()
        for short in shorts:
            avail = [w for w in hiding[short] if w not in used_words]
            if avail:
                chosen = random.choice(avail)
                picked.append((chosen, short))
                used_words.add(chosen)
            if len(picked) == 4:
                break

        if len(picked) == 4 and len(used_words) == 4:
            words = [p[0] for p in picked]
            if not is_dupe(words, past):
                hidden = [p[1] for p in picked]
                labels = {"start": "STARTING", "end": "ENDING", "inside": "HIDDEN IN"}
                results.append({
                    "group": f"{labels[mode]} WORDS THAT RHYME",
                    "members": [w.upper() for w in words],
                    "explanation": (
                        ", ".join(f"{w.upper()} → {h.upper()}" for w, h in picked)
                        + f" — {', '.join(h.upper() for h in hidden)} all rhyme"
                    ),
                    "type": f"twolayer_rhyme_{mode}"})
    return results


def gen_hidden_drop(hiding, past, common, count, mode):
    """4 words each hiding a DIFFERENT short word — those all shrink to the SAME word."""
    drop_groups = defaultdict(list)
    for short in hiding:
        if len(short) < 4: continue
        for i in range(len(short)):
            shorter = f"{short[:i]}{short[i+1:]}"
            if shorter in common:
                drop_groups[shorter].append(short)

    good = {k: list(set(v)) for k, v in drop_groups.items() if len(set(v)) >= 4}
    keys = list(good.keys())
    random.shuffle(keys)

    results = []
    for target in keys:
        if len(results) >= count:
            break
        shorts = good[target]
        random.shuffle(shorts)

        picked, used_words = [], set()
        for short in shorts:
            avail = [w for w in hiding.get(short, []) if w not in used_words]
            if avail:
                picked.append((random.choice(avail), short))
                used_words.add(picked[-1][0])
            if len(picked) == 4:
                break

        if len(picked) == 4 and len(used_words) == 4:
            words = [p[0] for p in picked]
            if not is_dupe(words, past):
                hidden = [p[1] for p in picked]
                results.append({
                    "group": f"HIDDEN WORDS SHRINK TO \"{target.upper()}\"",
                    "members": [w.upper() for w in words],
                    "explanation": (
                        ", ".join(f"{w.upper()} → {h.upper()}" for w, h in picked)
                        + f" — all become \"{target.upper()}\" minus a letter"
                    ),
                    "type": f"twolayer_drop_{mode}"})
    return results


# ================================================================
# TIER 3: INHERENTLY PURPLE
# ================================================================

def gen_compounds(common, past, count):
    results = []
    connectors = [w for w in common if 3 <= len(w) <= 7]
    random.shuffle(connectors)

    for conn in connectors[:600]:
        if len(results) >= count: break
        for pattern, fmt_group, fmt_expl in [
            (lambda w: f"{w}{conn}", f"___ {conn.upper()}", lambda pairs: ", ".join(p[1].upper() for p in pairs)),
            (lambda w: f"{conn}{w}", f"{conn.upper()} ___", lambda pairs: ", ".join(p[1].upper() for p in pairs)),
        ]:
            hits = [(w, pattern(w)) for w in common
                    if w != conn and len(w) >= 3 and pattern(w) in common]
            if len(hits) >= 4:
                picked = random.sample(hits, 4)
                words = [p[0] for p in picked]
                if not is_dupe(words, past):
                    results.append({
                        "group": fmt_group, "members": [w.upper() for w in words],
                        "explanation": fmt_expl(picked), "type": "compound"})
                    break
    return results


def gen_reversals(common, past, count):
    # use itertools.combinations to find reversal pairs without nested loops
    rev_words = {w for w in common if len(w) >= 3 and w[::-1] in common and w[::-1] != w}
    pairs = [(w, w[::-1]) for w in rev_words if w < w[::-1]]  # canonical ordering

    if len(pairs) < 4:
        return []
    random.shuffle(pairs)
    picked = pairs[:4]
    # randomly pick which direction to show
    words = [random.choice([a, b]) for a, b in picked]
    if is_dupe(words, past):
        return []

    return [{"group": "SPELLED BACKWARDS = ANOTHER WORD",
             "members": [w.upper() for w in words],
             "explanation": ", ".join(
                 f"{w.upper()} ← {w[::-1].upper()}" for w in words),
             "type": "reversal"}]


def gen_homophones(common, past, w2p, p2w, count):
    # find all homophone pairs where both words are common
    pairs = set()
    for w in common:
        for pron in w2p.get(w, []):
            for h in p2w.get(pron, []):
                if h != w and h in common:
                    pairs.add(tuple(sorted([w, h])))

    pairs = list(pairs)
    if len(pairs) < 4:
        return []
    random.shuffle(pairs)
    picked = pairs[:4]
    words = [p[0] for p in picked]
    if is_dupe(words, past):
        return []

    return [{"group": "EACH SOUNDS LIKE A DIFFERENT WORD",
             "members": [w.upper() for w in words],
             "explanation": ", ".join(f"{a.upper()} = {b.upper()}" for a, b in picked),
             "type": "homophone"}]


def gen_anagrams(common, past, count):
    # group by sorted letters, then use combinations() for pairs
    by_letters = defaultdict(list)
    for w in common:
        by_letters["".join(sorted(w))].append(w)

    pairs = [pair for group in by_letters.values() if len(group) >= 2
             for pair in combinations(group, 2)]

    if len(pairs) < 4:
        return []
    random.shuffle(pairs)
    picked = pairs[:4]
    words = [p[0] for p in picked]
    if is_dupe(words, past):
        return []

    return [{"group": "EACH IS AN ANAGRAM OF ANOTHER WORD",
             "members": [w.upper() for w in words],
             "explanation": ", ".join(f"{a.upper()} ↔ {b.upper()}" for a, b in picked),
             "type": "anagram"}]


def gen_letter_drop(common, past, count):
    # group by what you get when you remove one letter
    groups = defaultdict(list)
    for w in common:
        if len(w) < 4: continue
        # use a set comp to avoid duplicate shortened forms from the same word
        for shorter in {f"{w[:i]}{w[i+1:]}" for i in range(len(w))}:
            if shorter in common:
                groups[shorter].append(w)

    return [
        {"group": f"EACH MINUS A LETTER = \"{target.upper()}\"",
         "members": [w.upper() for w in words],
         "explanation": ", ".join(f"{w.upper()} → {target.upper()}" for w in words),
         "type": "letter_drop"}
        for target, words in pick_from_groups(groups, past, count)
    ]


# ---- main ----

def main():
    parser = argparse.ArgumentParser(description="Purple Connections generator")
    parser.add_argument("--words", default="words.txt")
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if not sync_repo() and not os.path.isfile(DATA_FILE):
        print(f"No puzzle data. Run: git clone {REPO_URL}")
        return

    common = load_words(args.words)
    past = load_past()
    w2p, p2w = build_pron()

    # build hiding maps for two-layer generators
    hiding = {mode: build_hiding(common, mode) for mode in ["start", "end", "inside"]}

    # all generators — tier 1, 2, 3
    all_results = []

    # tier 1: meta
    for gen in [gen_same_vowel, gen_keyboard, gen_contains_number,
                gen_doubles, gen_alternating, gen_secret_split, gen_chop_first]:
        all_results += gen(common, past, args.count)

    for gen in [gen_s_front, gen_swap_ends]:
        all_results += gen(common, past, args.count)

    # tier 2: two-layer
    for mode in ["inside", "start", "end"]:
        all_results += gen_hidden_rhyme(hiding[mode], past, w2p, args.count, mode)
    all_results += gen_hidden_drop(hiding["start"], past, common, args.count, "start")

    # tier 3: inherently purple
    all_results += gen_compounds(common, past, args.count)
    all_results += gen_letter_drop(common, past, args.count)
    all_results += gen_reversals(common, past, args.count)
    all_results += gen_homophones(common, past, w2p, p2w, args.count)
    all_results += gen_anagrams(common, past, args.count)

    for i, g in enumerate(all_results, 1):
        print(f"[{i}] {g['group']}  ({g['type']})")
        print(f"    {', '.join(g['members'])}")
        print(f"    {g['explanation']}\n")

    with open("purple_output.json", "w") as f:
        json.dump(all_results, f, indent=2)


if __name__ == "__main__":
    main()

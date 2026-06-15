# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the 40-item mock listings dataset (`data/listings.json`) for items matching a free-text description, then narrows by optional size and price filters. It is the only tool that touches the dataset; everything downstream operates on the item it returns.

**Input parameters:**
- `description` (str): Free-text keywords describing the desired item, e.g. `"vintage graphic tee"`. Tokenized and matched against each listing's `title`, `description`, `style_tags`, and `category`.
- `size` (str | None): Size to filter by, e.g. `"M"`. Matched case-insensitively as a substring so `"M"` matches `"S/M"` and `"M/L"`. `None` skips size filtering.
- `max_price` (float | None): Inclusive price ceiling. A listing passes if `price <= max_price`. `None` skips price filtering.

**What it returns:**
A `list[dict]` of full listing dicts (fields: `id, title, description, category, style_tags, size, condition, price, colors, brand, platform`), sorted by a relevance score (count of query keywords that overlap the listing's searchable text), highest first. Listings with a score of 0 are dropped. Returns `[]` when nothing matches — never raises.

**What happens if it fails or returns nothing:**
Returns an empty list `[]`. The planning loop detects the empty list, writes a specific message into `session["error"]` (naming the description/size/price that produced no matches and suggesting the user loosen a filter), and returns the session early **without** calling `suggest_outfit`.

---

### Tool 2: suggest_outfit

**What it does:**
Takes the selected listing and the user's wardrobe and asks the Groq LLM (`llama-3.3-70b-versatile`) to compose 1–2 complete outfits that pair the new item with named pieces the user already owns.

**Input parameters:**
- `new_item` (dict): A listing dict (typically `search_results[0]`). The prompt uses its `title`, `category`, `colors`, and `style_tags`.
- `wardrobe` (dict): A wardrobe dict with an `items` key — a list of `{id, name, category, colors, style_tags, notes}`. May have an empty `items` list.

**What it returns:**
A non-empty `str` of 1–2 outfit suggestions that reference the new item plus specific wardrobe pieces by name, with a short styling tip (e.g. cuff/tuck/layering).

**What happens if it fails or returns nothing:**
- **Empty wardrobe** (`wardrobe["items"]` is empty): the tool switches to a "general styling advice" prompt and returns advice on what kinds of pieces pair well with the item and what vibe it suits — it does not crash or return `""`.
- **LLM/network error:** caught in a `try/except`; returns a graceful fallback string (e.g. "Couldn't generate an outfit right now, but this <item> would pair well with neutral basics.") so the loop can still proceed to the fit card.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion + item details into a short, casual, shareable caption — the kind of thing someone captions an OOTD/thrift-haul post with. Uses the LLM at a higher temperature so repeated calls produce varied captions.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`.
- `new_item` (dict): The listing dict, used so the caption can name the item, price, and platform naturally (once each).

**What it returns:**
A `str` of 2–4 casual sentences usable as an Instagram/TikTok caption. Varies between calls for the same input (temperature ≈ 0.9).

**What happens if it fails or returns nothing:**
- **Empty / whitespace-only `outfit`:** guarded up front — returns a descriptive error string ("Can't write a fit card without an outfit suggestion to base it on.") rather than calling the LLM or raising.
- **LLM/network error:** caught; returns a simple fallback caption built from the item fields so the user still gets something shareable.

---

### Additional Tools (if any)

None for the required build. (Candidate stretch tool: `compare_price(item)` — estimates whether a price is fair against same-category listings. Will update this section before implementing it.)

---

## Planning Loop

**How does your agent decide which tool to call next?**

`run_agent(query, wardrobe)` runs a linear loop with one **conditional early-exit branch** driven by tool output, all coordinated through the `session` dict:

1. **Parse** the query into `description`, `size`, `max_price` (regex: a `$NN`/`under NN` pattern → `max_price`; a `size X` pattern or known size token → `size`; the remaining words → `description`). Store in `session["parsed"]`.
2. **Call `search_listings`** with the parsed params; store the list in `session["search_results"]`.
3. **Branch (the decision point):**
   - **If `search_results == []`** → set `session["error"]` to a specific message and **return immediately**. `suggest_outfit` and `create_fit_card` are *not* called. This is what makes the loop responsive rather than a fixed pipeline.
   - **Else** → set `session["selected_item"] = search_results[0]` and continue.
4. **Call `suggest_outfit(selected_item, wardrobe)`** → store `session["outfit_suggestion"]`.
5. **Call `create_fit_card(outfit_suggestion, selected_item)`** → store `session["fit_card"]`.
6. **Return `session`.**

The loop "knows it's done" when it either returns early on the empty-results branch or reaches step 6 with `fit_card` populated. Behavior visibly differs by input: an impossible query stops after step 3 with only `error` set; a valid query produces all three outputs.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (created by `_new_session()`) is the single source of truth for one interaction. Each step *reads* what prior steps wrote and *writes* its own result:

- `query` / `parsed` — the raw query and extracted search params.
- `search_results` — output of `search_listings`.
- `selected_item` — `search_results[0]`; the exact same dict object is passed into both `suggest_outfit` and `create_fit_card` (no re-entry, no re-querying).
- `wardrobe` — supplied at session creation, read by `suggest_outfit`.
- `outfit_suggestion` — output of `suggest_outfit`; passed verbatim into `create_fit_card`.
- `fit_card` — final output.
- `error` — `None` on success; a message string when the loop exits early.

Because every tool result lands in `session` before the next tool runs, downstream tools never ask the user to re-enter anything. `app.py`'s `handle_query()` reads the finished `session` and maps `selected_item`, `outfit_suggestion`, and `fit_card` to the three UI panels (or `error` to the first panel).

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Returns `[]`; loop sets `session["error"]` = "No listings matched 'X' (size Y, under $Z). Try removing the size filter or raising your price." and returns early without calling the other tools. |
| suggest_outfit | Wardrobe is empty | Detects empty `items`, switches to a general-styling-advice prompt, and returns useful advice for the item instead of crashing or returning `""`. (LLM/network errors are caught and return a neutral fallback suggestion.) |
| create_fit_card | Outfit input is missing or incomplete | Guards an empty/whitespace `outfit` and returns a descriptive error string instead of calling the LLM. (LLM/network errors are caught and return a fallback caption built from the item fields.) |

---

## Architecture

```
                     User query  +  wardrobe choice  (app.py)
                              │
                              ▼
        ┌──────────────────────────────────────────────────────────┐
        │              run_agent()  — Planning Loop (agent.py)        │
        │   session = { query, parsed, search_results,               │
        │               selected_item, wardrobe,                     │
        │               outfit_suggestion, fit_card, error }         │
        └──────────────────────────────────────────────────────────┘
                              │
        1. parse query → session["parsed"] = {description, size, max_price}
                              │
                              ▼
        2. search_listings(description, size, max_price)  ───────────┐
                              │                                       │ reads/writes
              search_results == [] ?                                  ▼
                ├── YES ─► session["error"] = "No listings..."   ┌─────────────┐
                │         RETURN session (early)  ──────────────►│   session    │
                │                                                 │   (state)    │
                └── NO ─► session["selected_item"] = results[0]   └─────────────┘
                              │                                       ▲
                              ▼                                       │
        3. suggest_outfit(selected_item, wardrobe)  [LLM] ───────────┤
                              │  session["outfit_suggestion"] = "..." │
                              ▼                                       │
        4. create_fit_card(outfit_suggestion, selected_item) [LLM] ──┘
                              │  session["fit_card"] = "..."
                              ▼
                       RETURN session
                              │
                              ▼
            app.py handle_query() maps session → 3 UI panels
            (error → panel 1; else listing / outfit / fit card)
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**
I'll use **Claude (Claude Code)**. For each tool I'll paste that tool's spec block above (what it does, the typed inputs, the return value, the failure mode) and ask it to implement the function in `tools.py`, using `load_listings()` from the data loader for Tool 1 and the Groq client (`llama-3.3-70b-versatile`) for Tools 2 and 3. **Verification before trusting it:** confirm `search_listings` filters by all three params and returns `[]` (not `None`/exception) on no match; confirm `suggest_outfit` branches on an empty wardrobe; confirm `create_fit_card` guards an empty `outfit`. Then run `pytest tests/` — at minimum a results test, an empty-results test, and a price-filter test must pass.

**Milestone 4 — Planning loop and state management:**
I'll give Claude the **Planning Loop** + **State Management** sections and the **Architecture** diagram above and ask it to implement `run_agent()` in `agent.py`. **Verification:** the generated code must branch on `search_results == []` (early return, no downstream calls), must store every intermediate in `session`, and must pass the same `selected_item` object into both LLM tools. I'll run `python agent.py` and confirm the happy path fills all fields and the no-results case leaves `fit_card` as `None` with `error` set.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse:** `run_agent` extracts `description="vintage graphic tee"`, `size=None`, `max_price=30.0` into `session["parsed"]`.

**Step 2 — Search:** Calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. Returns the matching tees under $30 sorted by keyword overlap (e.g. the Y2K "graphic tee" / "vintage"-tagged listings). The list is non-empty, so `session["selected_item"]` = the top result (e.g. *Y2K Baby Tee — Butterfly Print, $18, depop*).

**Step 3 — Suggest outfit:** Calls `suggest_outfit(selected_item, example_wardrobe)`. The LLM pairs the tee with named wardrobe pieces — e.g. *"Tuck it into your baggy straight-leg jeans and finish with chunky sneakers for a relaxed Y2K street look; roll the sleeves once for shape."* Stored in `session["outfit_suggestion"]`.

**Step 4 — Fit card:** Calls `create_fit_card(outfit_suggestion, selected_item)`. The LLM returns a casual caption, e.g. *"found this y2k butterfly baby tee on depop for $18 and it was made for my baggy jeans 🦋 full fit on my story."* Stored in `session["fit_card"]`.

**Final output to user:** The three Gradio panels show: (1) the listing — title, price, platform, condition; (2) the outfit idea; (3) the fit card. `session["error"]` is `None`.

**Error path:** For "designer ballgown size XXS under $5", `search_listings` returns `[]`. The loop sets `session["error"]` = "No listings matched 'designer ballgown' (size XXS, under $5). Try removing the size filter or raising your price." and returns early — `outfit_suggestion` and `fit_card` stay `None`, and the UI shows the message in panel 1.

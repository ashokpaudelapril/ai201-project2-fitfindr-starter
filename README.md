# FitFindr 🛍️

FitFindr is a multi-tool AI agent that helps you find secondhand clothing and
figure out how to wear it. You describe what you want in plain language; the
agent searches a mock listings dataset, suggests an outfit using your existing
wardrobe, and writes a shareable "fit card" caption — deciding what to do at
each step based on what the previous tool returned.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root (never commit it — it's gitignored):

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com). The LLM-backed
tools use Groq's `llama-3.3-70b-versatile`.

## Running it

```bash
python app.py          # launch the Gradio UI (open the URL it prints)
python agent.py        # run the CLI happy-path + no-results demo
pytest tests/          # run the tool unit tests
```

---

## Tool Inventory

| Tool | Inputs | Output | Purpose |
|------|--------|--------|---------|
| **search_listings** | `description (str)`, `size (str \| None)`, `max_price (float \| None)` | `list[dict]` of matching listings sorted by relevance (empty list if none) | Filters the 40-item dataset by price + size, then ranks by keyword overlap. The only tool that touches the data. |
| **suggest_outfit** | `new_item (dict)`, `wardrobe (dict)` | `str` — 1–2 outfit suggestions | Asks the LLM to pair the found item with named wardrobe pieces (or gives general advice if the wardrobe is empty). |
| **create_fit_card** | `outfit (str)`, `new_item (dict)` | `str` — a casual 2–4 sentence caption | Turns the outfit into a shareable OOTD-style caption mentioning the item, price, and platform. Uses higher temperature so output varies. |

Each listing dict contains: `id, title, description, category, style_tags,
size, condition, price, colors, brand, platform`. These inputs/outputs match
the actual function signatures in [tools.py](tools.py).

---

## How the Planning Loop Works

`run_agent(query, wardrobe)` in [agent.py](agent.py) is a linear loop with one
**conditional early-exit branch** driven by tool output — not a fixed pipeline:

1. **Parse** the query (`parse_query`, regex) into `description`, `size`, and
   `max_price`.
2. **Call `search_listings`** with those parameters.
3. **Branch — the decision point:**
   - If the result list is **empty**, write a specific message into
     `session["error"]` and **return immediately**. `suggest_outfit` and
     `create_fit_card` are never called with empty input.
   - Otherwise, set `selected_item = search_results[0]` and continue.
4. **Call `suggest_outfit`** with the selected item + wardrobe.
5. **Call `create_fit_card`** with the outfit suggestion + selected item.
6. **Return** the session.

Because step 3 branches on what `search_listings` returned, the agent behaves
differently per input: an impossible query stops after step 3 with only
`error` set; a valid query produces all three outputs.

---

## State Management

A single `session` dict (built by `_new_session()`) is the source of truth for
one interaction. Each step reads what earlier steps wrote and writes its own
result:

| Field | Written by | Read by |
|-------|-----------|---------|
| `query`, `parsed` | session init / parse step | search |
| `search_results` | `search_listings` | branch logic |
| `selected_item` | branch (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | session init | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | UI |
| `error` | branch / never | UI (decides which panels show) |

The **same `selected_item` dict object** is passed into both LLM tools — verified
with `session["selected_item"] is session["search_results"][0]` → `True`. The
user never re-enters anything. `handle_query()` in [app.py](app.py) reads the
finished session and maps it to the three UI panels (or the error to panel 1).

---

## Error Handling (per tool)

| Tool | Failure mode | Response |
|------|-------------|----------|
| **search_listings** | No listings match | Returns `[]` (never raises). The loop sets a specific `error` naming the filters and stops before the LLM tools. |
| **suggest_outfit** | Empty wardrobe | Switches to a general-styling-advice prompt and returns useful advice. LLM/network errors are caught and return a neutral fallback. |
| **create_fit_card** | Empty/whitespace outfit | Guarded up front — returns a descriptive error string instead of calling the LLM. LLM/network errors return a fallback caption built from item fields. |

**Concrete example from testing** — triggering the empty-outfit guard:

```
$ python -c "from tools import search_listings, create_fit_card;
  r = search_listings('vintage graphic tee', size=None, max_price=50);
  print(create_fit_card('', r[0]))"

Can't write a fit card without an outfit suggestion to base it on — run suggest_outfit first.
```

And the no-results path through the full agent:

```
No listings matched your search (size XXS, under $5). Try removing the size
filter, raising your price, or using different keywords.
```

---

## Spec Reflection

- **One way the spec helped:** Writing the tool I/O and the error-handling table
  in `planning.md` first meant each tool had an unambiguous contract before any
  code existed — implementation was mostly transcription, and the failure modes
  were designed rather than bolted on. The agent diagram made the early-return
  branch obvious to wire up.
- **One way implementation diverged:** The spec suggested the planning loop might
  parse the query with the LLM. I used **regex instead** (`parse_query`) because
  it's deterministic, free of an extra API call, and trivially unit-testable.
  `search_listings` already drops stopwords/numbers, so leaving filter words in
  the description string is harmless — simpler than fully stripping them.

---

## AI Usage

1. **Implementing the three tools (Milestone 3).** I gave Claude (Claude Code)
   each tool's spec block from `planning.md` — typed inputs, return value, and
   failure mode — and asked it to implement them in `tools.py` using
   `load_listings()` for Tool 1 and the Groq client for Tools 2–3. I verified the
   output by checking that `search_listings` filtered by all three params and
   returned `[]` (not `None`) on no match, that `suggest_outfit` branched on an
   empty wardrobe, and that `create_fit_card` guarded an empty outfit — then ran
   `pytest tests/` (10 tests passing). I kept the keyword-overlap scoring but
   added a stopword set so query filler words ("looking", "for") don't inflate
   scores.

2. **Wiring the planning loop (Milestone 4).** I gave Claude the Planning Loop +
   State Management sections and the architecture diagram and asked it to
   implement `run_agent()`. I verified it branches on `search_results == []` with
   an early return (no downstream calls), stores every intermediate in `session`,
   and passes the same `selected_item` object into both LLM tools (confirmed with
   an `is` identity check). I tightened the no-results error message to name the
   active filters so it's actionable rather than generic.

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example/empty wardrobe
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tests/
│   └── test_tools.py          # pytest tests (one+ per failure mode)
├── tools.py                   # the three tools
├── agent.py                   # parse_query() + run_agent() planning loop
├── app.py                     # Gradio UI (handle_query)
├── planning.md                # design spec (written before implementation)
└── requirements.txt
```

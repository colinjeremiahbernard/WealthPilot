# WealthPilot — Investment Assistant (RPA + n8n + IA)

Rebuilt, self-contained version of the DIO lab challenge: a Python scraper
extracts client data, forwards it to an n8n workflow, which cross-references
each client's investor profile against a set of investment options and
generates a personalized recommendation message (static template or LLM-generated).

## Architecture

```
docs/index.html (clients)  --scrape-->  src/extract_clients.py  --POST-->  n8n Webhook
                                                                                 |
docs/data.csv (options)  <---fetch--- n8n workflow -------------------------------
                                                                                 |
                                             match profile -> generate message (AI or static)
                                                                                 |
                                                                          JSON response
```

## Project structure

```
WealthPilot/
├── README.md
├── requirements.txt
├── .env.example
├── src/
│   └── extract_clients.py   # RPA: scrapes clients, POSTs to n8n webhook
├── docs/
│   ├── index.html           # sample clients page (swap for your real source)
│   └── data.csv             # investment options by profile
└── n8n/
    └── workflow.json        # importable n8n workflow
```

## Setup

1. **Install Python dependencies**
   ```bash
   python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   cp .env.example .env
   ```

2. **Import the workflow into n8n**
   - Open your n8n instance → *Workflows* → *Import from File* → select `n8n/workflow.json`.
   - Open the **Webhook - Receive Clients** node, copy its Production URL, and paste it into `.env` as `N8N_WEBHOOK_URL`.
   - Update the **Fetch Investment Options (CSV)** node's URL to point at wherever you host `docs/data.csv` (GitHub Pages, a raw GitHub URL, or a local n8n-reachable path).

3. **(Optional) Enable AI-generated messages**
   - Add an `anthropicApi` credential in n8n (or swap the `AI Agent - Generate Message` node's URL/auth for OpenAI/Gemini).
   - Set the environment variable `USE_AI_MESSAGES=true` in your n8n instance to route through the AI branch instead of the static templates. Leave unset (or `false`) to use the free static templates.

4. **Run the scraper**
   ```bash
   # Test parsing only, no network call:
   python src/extract_clients.py --source docs/index.html --dry-run

   # Send to n8n:
   python src/extract_clients.py --source docs/index.html
   ```
   Swap `--source` for a live URL (e.g. your GitHub Pages clients page) when you're ready to go beyond the local sample data.

## Notes on the rebuild vs. the original lab

- The Python script now validates and retries, uses dataclasses/type hints, and supports both local files and remote URLs — so you can develop and test entirely offline before pointing it at a real hosted page.
- The n8n workflow includes both the MVP (static message templates) and the stretch goal (LLM-generated messages) as parallel branches behind a single toggle (`USE_AI_MESSAGES`), instead of requiring a full rebuild to add AI later.
- `docs/index.html` and `docs/data.csv` are included as ready-to-use sample data so the whole pipeline runs end-to-end without needing GitHub Pages hosting first.

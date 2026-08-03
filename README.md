# Job Tracker — France Travail + Claude

A small script that pulls live job postings from France Travail's official API,
scores each one against your profile using Claude, and appends the results to a CSV —
so you get a running, de-duplicated shortlist instead of manually re-checking job boards.

## How it works

1. Queries the [France Travail "Offres d'emploi v2" API](https://francetravail.io) with a set of
   keywords (edit the `queries` list in `get_all_opportunities()` to match your own field).
2. De-duplicates results — both against jobs seen in previous runs, and across overlapping
   keyword searches within the same run.
3. Sends each new job snippet to Claude along with your profile, and gets back a structured
   match score plus a short rationale.
4. Appends everything to `Job_Results_FranceTravail.csv`, so re-running the script only adds
   genuinely new postings.

## 1. Prerequisites

- Python 3.9+
- A France Travail (francetravail.io) account
- An Anthropic Console account with API billing enabled

## 2. Install dependencies

```bash
pip install requests python-dotenv anthropic pandas
```

## 3. Create your France Travail API application

1. Go to [francetravail.io](https://francetravail.io) and log in (or create an account).
2. Navigate to **"Créer une application"**.
3. Fill in the form:
   - **Nom de votre application** — any label, e.g. `job-tracker`.
   - **Description** — a short sentence describing the project.
   - **URL de votre site utilisant les données des API** — this field rejects local
     addresses (`localhost`, local IPs). Use a public URL you own, e.g. your GitHub
     profile (`https://github.com/<your-username>`).
4. Once created, open your application's page and click **"Ajouter une API"**, then
   subscribe to **"Offres d'emploi v2"**. This grants the `api_offresdemploiv2` scope —
   without this step, authentication will succeed but job searches will fail.
5. On the application page you'll find:
   - **Identifiant client** → this is your `FT_CLIENT_ID`
   - **Clé secrète** → this is your `FT_CLIENT_SECRET`, shown **only once** at creation.
     If you lose it, use "renouveler vos identifiants" to generate a new one.

## 4. Create your Anthropic API key

1. Go to the [Anthropic Console](https://console.anthropic.com) and create an account
   (separate from a normal claude.ai account — this is for API/billing access).
2. Add billing details under **Settings → Billing**. You can also set a spend limit
   there as a safety net.
3. Go to **API Keys** and generate a new key → this is your `ANTHROPIC_API_KEY`.
4. Verify the model string used in the script (`client.messages.create(model=...)`)
   matches a currently available model — check the
   [Anthropic model list](https://docs.claude.com/en/docs/about-claude/models) if unsure,
   since model names are periodically updated.

## 5. Set up your `.env` file

Create a `.env` file in the project root (never commit this file):

```
FT_CLIENT_ID=your_france_travail_client_id
FT_CLIENT_SECRET=your_france_travail_client_secret
ANTHROPIC_API_KEY=your_anthropic_api_key
```

Add `.env` to your `.gitignore` if it isn't already there.

## 6. Create your profile

Create a `my_profile.md` file in the project root with a written summary of your
background — degrees, experience, skills, tools, languages, and what you're looking for
(contract type, location constraints, seniority). This is the text Claude compares each
job against, so the more specific, the better the match scoring.

## 7. Run it

```bash
python main.py
```

Each run:
- Skips jobs already processed in previous runs (tracked in `seen_jobs.json`)
- Prints a live summary of duplicates skipped and new jobs found
- Appends results to `Job_Results_FranceTravail.csv`

## Notes on cost

- The script uses Claude's prompt caching (`cache_control: ephemeral`) on your profile
  text, so it's only charged in full on the first call per run — subsequent calls reuse
  the cached version at a steep discount.
- `max_tokens=2000` in the API call is a per-call output ceiling, not a shared budget —
  it doesn't accumulate or "run out" across calls.
- Setting a spend limit in the Anthropic Console (Settings → Billing) is the most
  reliable safety net regardless of call volume.

## Customizing for a different field

- `queries` in `get_all_opportunities()` — swap for keywords relevant to your own domain.
- `contract_type` — defaults to `"CDI"`; set to `None` to also include CDD and other
  contract types, or change to another France Travail contract code.
- `my_profile.md` — this is the main lever for match-score quality; keep it current.

## Known limitations

- France Travail's API mainly covers private-sector and public-institution postings
  declared to France Travail. CNRS research-engineer roles and PhD positions often go
  through separate channels not covered here — e.g. Euraxess, ABG (Association Bernard
  Gregory), ADUM, or direct lab/university career pages.
- Match scores and extracted fields depend on Claude's reading of the job snippet, which
  is sometimes short or incomplete — treat scores as a triage signal, not ground truth.
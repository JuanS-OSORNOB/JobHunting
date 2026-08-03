import os
from dotenv import load_dotenv
import requests
from dotenv import load_dotenv
import anthropic
import json
from datetime import date
import pandas as pd
import re
import json
today = date.today().isoformat()

# Load your API keys
load_dotenv()

FT_TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
FT_SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

_ft_token_cache = {"token": None}

def get_ft_access_token():
    """
    Client-credentials OAuth2 flow against France Travail.
    Requires FT_CLIENT_ID / FT_CLIENT_SECRET from a francetravail.io app
    subscribed to 'Offres d'emploi v2' (scope: api_offresdemploiv2 o2dsoffre).
    Caches the token in memory for the life of the process.
    """
    if _ft_token_cache["token"]:
        return _ft_token_cache["token"]

    payload = {
        "grant_type": "client_credentials",
        "client_id": os.getenv("FT_CLIENT_ID"),
        "client_secret": os.getenv("FT_CLIENT_SECRET"),
        "scope": "api_offresdemploiv2 o2dsoffre",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(FT_TOKEN_URL, data=payload, headers=headers)
    response.raise_for_status()
    token = response.json()["access_token"]
    _ft_token_cache["token"] = token
    return token

def get_job_listings(query, contract_type="CDI", max_results=50):
    """
    Queries the official France Travail 'Offres d'emploi v2' API.
    Returns live, structured postings (no expired/duplicate aggregator noise).
    contract_type: 'CDI', 'CDD', 'MIS', 'SAI', 'LIB' or None for all types.
    """
    token = get_ft_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "motsCles": query,
        "range": f"0-{max_results - 1}",  # API pagination is inclusive, max 149 per call
        "sort": 1,  # sort by most recent publication date
    }
    if contract_type:
        params["typeContrat"] = contract_type

    try:
        response = requests.get(FT_SEARCH_URL, headers=headers, params=params)
        # France Travail returns 200 (full page) or 206 (partial content) on success
        if response.status_code not in (200, 206):
            response.raise_for_status()
        return response.json().get("resultats", [])
    except Exception as e:
        print(f"An error occurred querying France Travail: {e}")
        return []

def get_all_opportunities(seen_jobs, contract_type="CDI"):
    queries = ["géophysicien", "ingénieur géophysique", "géologue ingénieur", "seismologue"]
    all_new_jobs = []
    # Seed with everything already processed in past runs, then keep updating
    # it live as we go so overlapping queries in THIS run don't duplicate each other.
    found_this_run = set(seen_jobs)
    duplicate_count = 0

    for q in queries:
        print(f"Searching for new opportunities: '{q}' ({contract_type or 'any contract'})...")
        results = get_job_listings(q, contract_type=contract_type)

        new_jobs = []
        for offer in results:
            offer_id = offer.get("id")  # France Travail's own offer id — more reliable than the URL
            link = offer.get("origineOffre", {}).get("urlOrigine") or offer_id
            dedupe_key = offer_id or link

            if not dedupe_key or dedupe_key in found_this_run:
                if dedupe_key: # only counts real duplicates, not missing keys
                    duplicate_count += 1
                continue
            found_this_run.add(dedupe_key)

            new_jobs.append({
                "id": offer_id,
                "title": offer.get("intitule"),
                "snippet": offer.get("description"),
                "link": link,
                "publication_date": offer.get("dateCreation"),
            })
        print(f"Found {len(results)} total jobs. {len(new_jobs)} are new.")
        all_new_jobs.extend(new_jobs)
    print(f"\nSummary: {len(all_new_jobs)} unique new jobs found, {duplicate_count} duplicates skipped across queries.")

    return all_new_jobs



client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def analyze_job(job_snippet, user_profile):
    system_instruction = f"""You are a data extraction assistant (expert career analyst).
    You MUST output ONLY valid JSON.
    1. Do not include any conversational filler.
    2. Do NOT include markdown code blocks (e.g., do not use ```json)
    3. Ensure the JSON is properly escaped (no unescaped newlines inside string values).
    4. If information is missing, set the value to "N/A".
    5. Format all dates as YYYY-MM-DD.
    6. The current date is {today}.
    """
    
    #prompt = f"""
    #Analyze the following job description snippet:
    #{job_snippet}
    #
    #Compare it against this user profile:
    #{user_profile}
    #
    #Calculate a match score as weighted average of:
    #  1) "Tech alignment" (40%): Matches between job tools and profile,
    #  2) "Experience level" (30%): Does the job seniority level matches the user profile?,
    #  3) "Domain relevance" (20%): Does the industry or role purpose matches the user profile background?, and
    #  4) "Constraints" (10%): Does location/remote policy fit the user profile requirements?
    #Return a JSON object with these keys: "title", "company", "seniority", "responsibilities", "skills_required", "tools_required", "language", "location", "match_score", "rationale", "publication_date", "date_of_search", "application_deadline".
    #"""
    
    # Create a list of objects to choose what to cache (the user profile)
    messages = [
        {
            "role": "user",
            "content": [
                # Here is the cached profile block
                {
                    "type": "text", 
                    "text": f"My Profile: {user_profile}", 
                    "cache_control": {"type": "ephemeral"}
                },
                # Here is the dynamic job snippet block
                {
                    "type": "text", 
                    "text": f"""
                    Analyze this job snippet: {job_snippet}.
                    Calculate a match_score as weighted average of:
                    1) "Tech alignment" (40%): Matches between job required tools and user profile,
                    2) "Experience level" (30%): Does the job seniority level matches the user profile?,
                    3) "Domain relevance" (20%): Does the industry or role purpose matches the user profile background?, and
                    4) "Constraints" (10%): Does location/remote policy fit the user profile requirements?
                    Remember that the value for the "match_score" key is an integer number, only return this.
                    After having completed the analysis and computation of the score return a JSON object with these keys (in this order please):
                    1) "title",
                    2) "company",
                    3) "seniority",
                    4) "responsibilities",
                    5) "skills_required",
                    6) "tools_required",
                    7) "language",
                    8) "location",
                    9) "match_score",
                    10) "rationale",
                    11) "publication_date",
                    12) "date_of_search",
                    13) "application_deadline"
                    """
                }
            ]
        }
    ]

    #Call the API
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=system_instruction, # This forces the persona
        #messages=[{"role": "user", "content": prompt}]
        messages = messages
    )
    
    content = response.content[0].text
    
    # Extract only the JSON part using Regex (searches for everything between { and })
    
    # Try to find the JSON
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"\n--- DEBUG: JSON Parse Error ---")
            print(f"Error: {e}")
            print(f"Raw Output: {content}") # See exactly what broke
            return {} # Return empty so the script continues
    else:
        print("\n--- DEBUG: No JSON found in output ---")
        print(f"Raw Output: {content}")
        return {}

# Load existing jobs cache
CACHE_FILE = "seen_jobs.json"

def load_seen_jobs():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return []

def save_seen_jobs(seen_jobs):
    with open(CACHE_FILE, "w") as f:
        json.dump(seen_jobs, f)

# --- Execution ---
#region Main
import time
from datetime import timedelta
if __name__ == "__main__":
    start = time.perf_counter()
    # 1. Load Data
    seen_jobs = load_seen_jobs()
    if not os.path.exists("job_results.csv"):
        print("CSV missing! Clearing cache to start fresh...")
        if os.path.exists("seen_jobs.json"):
            os.remove("seen_jobs.json")
    
    # 2. Load Profile
    with open("my_profile.md", "r") as f:
        my_profile = f.read()

    # 3. Search jobs via France Travail (set contract_type=None to also see CDD/other contracts)
    jobs = get_all_opportunities(seen_jobs, contract_type = "CDI")

    # 4. Analyze each job
    all_results = []
    counter = 0
    for job in jobs:
        print(f"\n\nPROCESSING JOB {counter + 1}/{len(jobs)}:")
        print(f"Title: {job.get('title')}")
        print(f"Publication Date: {job.get('publication_date')}")
        print(f"Snippet: {job.get('snippet')}")
        print(f"Link: {job.get('link')}")
        print(f"Analyzing...")
        raw_analysis = analyze_job(job.get('snippet'), my_profile)
        #raw_analysis['application_link'] = job.get('link') # Add the link back in the table
        analysis = {
            "ft_id": job.get("id"),#FranceTravail ID
            "title": raw_analysis.get("title"),
            "company": raw_analysis.get("company"),
            "seniority": raw_analysis.get("seniority"),
            "responsibilities": raw_analysis.get("responsibilities"),
            "skills_required": raw_analysis.get("skills_required"),
            "tools_required": raw_analysis.get("tools_required"),
            "language": raw_analysis.get("language"),
            "location": raw_analysis.get("location"),
            "match_score": raw_analysis.get("match_score"), # Use the final score
            "rationale": raw_analysis.get("rationale"),
            "publication_date": job.get('publication_date'),
            "date_of_search": raw_analysis.get("date_of_search"),
            "application_deadline": raw_analysis.get("application_deadline"),
            "link": job.get('link'),
        }
        #analysis["tech_score"] = raw_analysis.get("tech_alignment", {}).get("score", 0)
        all_results.append(analysis)
        # Update seen list immediately so if script crashes, we don't re-process
        seen_jobs.append(job.get('id') or job.get('link'))
        counter += 1
    
    save_seen_jobs(seen_jobs)
    # 5. Save to CSV for easy viewing
    if all_results:
        df = pd.DataFrame(all_results)
        before_count = len(df)
        df = df.drop_duplicates(subset=['ft_id'], keep='first')  # Second safety net (belt-and-suspenders); get_all_opportunities already dedupes upstream
        removed = before_count - len(df)
        print(f"Removed {removed} duplicate(s) at the final DataFrame stage.")
        filename = "Job_Results_FranceTravail.csv" 
        df.to_csv(filename, mode='a', index=False, header=not os.path.exists(filename))
        print(f"\nSuccess! Added {len(all_results)} new jobs to {filename}.")
    else:
        print("\nNo new jobs to process.")

    end = time.perf_counter()
    elapsed = end - start
    print(f"Execution time: {timedelta(seconds=round(elapsed))}")
#endregion Main
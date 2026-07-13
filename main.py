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

def get_job_listings(query, location):
    """
    Queries the Serper API for LinkedIn job results.
    """
    url = "https://google.serper.dev/search"
    
    # We use 'site:linkedin.com/jobs' to force Google to only show LinkedIn job pages
    payload = {
        "q": f"site:linkedin.com/jobs {query} in {location}",
        "num": 5  # Start with 5 results to avoid over-fetching
    }
    
    headers = {
        'X-API-KEY': os.getenv("SERPER_API_KEY"),
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status() # This will crash if the request fails (good for debugging)
        return response.json().get('organic', [])
    except Exception as e:
        print(f"An error occurred: {e}")
        return []
    

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
    
    # --- ADD THIS PARSING LOGIC BELOW ---
    
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
if __name__ == "__main__":
    # 1. Load Data
    seen_jobs = load_seen_jobs()
    if not os.path.exists("job_results.csv"):
        print("CSV missing! Clearing cache to start fresh...")
        if os.path.exists("seen_jobs.json"):
            os.remove("seen_jobs.json")
    
    # 2. Load Profile
    with open("my_profile.md", "r") as f:
        my_profile = f.read()

    # 3. Define your search criteria
    my_job_search = "Geophysical Researcher"
    my_location = "France"
    
    print(f"Searching for new opportunities: '{my_job_search}' in '{my_location}'...")
    
    # 4. Search jobs
    jobs = get_job_listings(my_job_search, my_location)
    new_jobs = [j for j in jobs if j.get('link') not in seen_jobs]
    print(f"Found {len(jobs)} total jobs. {len(new_jobs)} are new.")

    # 5. Analyze each job
    all_results = []
    for job in new_jobs:
        print(f"\nFound: {job.get('title')}")
        print(f"Snippet: {job.get('snippet')}")
        print(f"Link: {job.get('link')}")
        print(f"Analyzing...")
        raw_analysis = analyze_job(job.get('snippet'), my_profile)
        #raw_analysis['application_link'] = job.get('link') # Add the link back in the table
        analysis = {
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
            "publication_date": raw_analysis.get("publication_date"),
            "date_of_search": raw_analysis.get("date_of_search"),
            "application_deadline": raw_analysis.get("application_deadline"),
            "link": job.get('link'),
        }
        #analysis["tech_score"] = raw_analysis.get("tech_alignment", {}).get("score", 0)
        all_results.append(analysis)
        # Update seen list immediately so if script crashes, we don't re-process
        seen_jobs.append(job.get('link'))
    
    save_seen_jobs(seen_jobs)
    # 6. Save to CSV for easy viewing
    if all_results:
        df = pd.DataFrame(all_results)
        df.to_csv("job_results.csv", mode='a', index=False, header=not os.path.exists("job_results.csv"))
        print(f"\nSuccess! Added {len(all_results)} new jobs to job_results.csv.")
    else:
        print("\nNo new jobs to process.")
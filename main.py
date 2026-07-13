import os
from dotenv import load_dotenv
import os
import requests
from dotenv import load_dotenv

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
    
import anthropic
import json
import os

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def analyze_job(job_snippet, user_profile):
    system_instruction = "You are a data extraction assistant. You output ONLY valid JSON. Do not include any conversational filler, markdown formatting (like ```json), or explanations. Return strictly the JSON object."
    
    prompt = f"""
    Analyze the following job description snippet:
    {job_snippet}
    
    Compare it against this user profile:
    {user_profile}
    
    Return a JSON object with these keys: "title", "seniority", "skills_required", "match_score", "rationale".
    """
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=system_instruction, # This forces the persona
        messages=[{"role": "user", "content": prompt}]
    )
    
    content = response.content[0].text
    
    # --- ADD THIS PARSING LOGIC BELOW ---
    import re
    # Extract only the JSON part using Regex (searches for everything between { and })
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    
    if json_match:
        return json.loads(json_match.group())
    else:
        print("Failed to find JSON in response:", content)
        return {}

# --- Execution ---
if __name__ == "__main__":
    # 1. Load Profile
    with open("my_profile.txt", "r") as f:
        my_profile = f.read()

    # 2. Define your search criteria
    my_job_search = "Geophysical Researcher"
    my_location = "France"
    
    print(f"Searching for '{my_job_search}' in '{my_location}'...")
    # 3. Analyze each job
    jobs = get_job_listings(my_job_search, my_location)

    # 4. Analyze each job
    all_results = []
    for job in jobs:
        print(f"\nFound: {job.get('title')}")
        print(f"Snippet: {job.get('snippet')}")
        print(f"Link: {job.get('link')}")
        print(f"Analyzing: {job.get('title')}...")
        analysis = analyze_job(job.get('snippet'), my_profile)
        analysis['link'] = job.get('link') # Add the link back in
        all_results.append(analysis)
    
    # 5. Save to CSV for easy viewing
    import pandas as pd
    df = pd.DataFrame(all_results)
    df.to_csv("job_results.csv", index=False)
    print("Done! Open 'job_results.csv' to see your analyzed jobs.")
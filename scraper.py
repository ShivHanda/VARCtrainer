import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai
from datetime import datetime
import time
import re
import random
import sys

# --- CONFIG ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("CRITICAL ERROR: GEMINI_API_KEY not found.")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = 'gemini-2.5-flash' 

HEADERS = {
   'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

def get_smart_essay_selection():
    """
    Logic:
    1. Scrape the main Aeon essays webpage directly (since RSS is dead).
    2. Check 'data.json' to see what we scraped yesterday.
    3. If Latest == Yesterday's -> Pick RANDOM.
    4. If Latest != Yesterday's -> Pick LATEST.
    """
    url = "https://aeon.co/essays"
    print(f"Checking Main Essays Page: {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            print(f"ERROR: Aeon blocked request. Status: {response.status_code}")
            sys.exit(1) 

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all hyperlink tags on the page
        links = soup.find_all('a', href=True)
        essay_candidates = []

        for a in links:
            href = a['href']
            # We only want actual essay links, ignoring author pages, tags, etc.
            if '/essays/' in href and not any(x in href for x in ['/tag/', '/author/', '/topic/']):
                
                # Fix relative links
                full_link = href if href.startswith('http') else "https://aeon.co" + href
                
                # Extract a readable title
                title = a.get_text(strip=True)
                if len(title) < 10: 
                    # If the link text is just an image or short string, extract from the URL slug
                    title = full_link.split('/')[-1].replace('-', ' ').title()
                
                # Avoid duplicates
                if len(title) > 5 and not any(e['link'] == full_link for e in essay_candidates):
                    essay_candidates.append({
                        "link": full_link,
                        "title": title
                    })
        
        if not essay_candidates:
            print("ERROR: No essays found on the page! HTML structure might have changed.")
            sys.exit(1)

        # 1. Identify the absolute latest essay
        latest_essay = essay_candidates[0]
        
        # 2. Check what we scraped last time
        last_scraped_url = ""
        try:
            if os.path.exists('data.json'):
                with open('data.json', 'r') as f:
                    old_data = json.load(f)
                    last_scraped_url = old_data['metadata']['source']
        except Exception as e:
            print(f"Could not read previous data: {e}")

        # 3. DECISION TIME
        if latest_essay['link'] == last_scraped_url:
            print("⚠️ Latest essay is same as yesterday. Switching to RANDOM mode.")
            if len(essay_candidates) > 1:
                selected = random.choice(essay_candidates[1:])
            else:
                selected = essay_candidates[0]
        else:
            print("✅ New essay detected! Fetching LATEST.")
            selected = latest_essay

        print(f"Selected: {selected['title']}")
        return selected['link'], selected['title']

    except Exception as e:
        print(f"CRITICAL: Scrape Logic Failed entirely: {e}")
        sys.exit(1)

def scrape_text_from_url(url):
    print(f"Scraping Text: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        article_body = soup.find('div', class_='article__body')
        if not article_body: article_body = soup
        paragraphs = [p.get_text(strip=True) for p in article_body.find_all('p')]
        clean_text = [p for p in paragraphs if len(p.split()) > 25 and "subscribe" not in p.lower()]
        if not clean_text: return None
        return clean_text
    except Exception as e:
        print(f"Scrape Error: {e}")
        return None

def generate_analysis_real(text_chunk):
    print(f"Calling AI Model: {MODEL_NAME}...")
    model = genai.GenerativeModel(MODEL_NAME)
    
    # --- FIX: STRICT JSON SCHEMA ---
    # This configuration forces the model to return ONLY valid JSON.
    generation_config = {
        "response_mime_type": "application/json",
    }

    prompt = f"""
    You are a CAT (Common Admission Test) Exam Setter. Analyze this text carefully.
    
    TEXT:
    {text_chunk[:3500]}
    
    TASK:
    1. Identify the Author's Tone (e.g., Critical, Satirical, Informative, Acerbic).
    2. Write a 1-sentence Summary of this specific chunk.
    3. Create 3 Reading Comprehension Questions (1 Inference, 1 Main Idea, 1 Detail).
    
    Output must be a JSON object with this schema:
    {{
        "tone": "String",
        "summary": "String",
        "questions": [
            {{
                "question": "String",
                "options": ["A", "B", "C", "D"],
                "correct_index": Integer (0-3),
                "explanation": "String"
            }}
        ]
    }}
    """
    
    try:
        # Applying the config here
        response = model.generate_content(prompt, generation_config=generation_config)
        
        # Now response.text is GUARANTEED to be JSON. No Regex needed.
        data = json.loads(response.text)
        return data
        
    except Exception as e:
        print(f"AI Gen Error: {e}")
        # Print the raw text to see WHY it failed if it happens again
        if 'response' in locals():
            print(f"Raw Output: {response.text}") 
        return None

def main():
    # 1. Get Smart Selection
    url, title = get_smart_essay_selection()
    if not url: return

    # 2. Scrape Text
    paragraphs = scrape_text_from_url(url)
    if not paragraphs: return

    # 3. Chunking
    chunks = []
    current = []
    w_count = 0
    for p in paragraphs:
        current.append(p)
        w_count += len(p.split())
        if w_count > 600:
            chunks.append("\n\n".join(current))
            current = []
            w_count = 0
    if current: chunks.append("\n\n".join(current))

    # 4. Analysis
    final_passages = []
    print(f"Analyzing {len(chunks)} passages...")
    
    for i, chunk in enumerate(chunks):
        print(f"Processing Chunk {i+1}...")
        analysis = generate_analysis_real(chunk)
        
        if not analysis:
            print(f"⚠️ Warning: Analysis failed for chunk {i+1}")
            analysis = {"tone": "Analytical", "summary": "Analysis unavailable due to AI error.", "questions": []}

        final_passages.append({
            "id": i+1,
            "text": chunk,
            "tone": analysis.get("tone", "Neutral"),
            "summary": analysis.get("summary", "No summary available."),
            "questions": analysis.get("questions", [])
        })
        # Sleep slightly longer to avoid rate limits
        time.sleep(5) 

    data = {
        "metadata": {
            "title": title,
            "source": url,
            "date_scraped": str(datetime.now().date())
        },
        "passages": final_passages
    }
    
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)
    print("Success: Smart update complete.")

if __name__ == "__main__":
    main()

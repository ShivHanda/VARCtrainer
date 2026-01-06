import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai
from datetime import datetime
import time

# --- CONFIG ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# HARDCODED URL FOR STABILITY
# We will target this specific essay first to ensure the system works.
TARGET_URL = "https://aeon.co/essays/what-can-stone-age-tool-making-tell-us-about-the-evolution-of-language"

def scrape_essay(url):
    print(f"Scraping: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch page: {e}")
        return "Error", []

    soup = BeautifulSoup(response.content, 'html.parser')

    # Get Title
    title_tag = soup.find('h1')
    title = title_tag.get_text(strip=True) if title_tag else "Aeon Essay (Title Not Found)"
    
    # BRUTE FORCE TEXT EXTRACTION
    # Instead of looking for a specific div, we look for ALL <p> tags.
    # We then filter them. If a paragraph has > 30 words, it's likely essay content.
    all_p = soup.find_all('p')
    clean_text = []
    
    for p in all_p:
        text = p.get_text(strip=True)
        # Filter out menu items, footers, and short captions
        if len(text.split()) > 30: 
            clean_text.append(text)
            
    if not clean_text:
        print("WARNING: No text found. The scraper failed to identify paragraphs.")
        # Fallback for testing only
        clean_text = ["This is a fallback paragraph because the scraper failed to read the website HTML structure properly."]

    return title, clean_text

def chunk_text(paragraphs, chunk_size=550):
    chunks = []
    current_chunk = []
    word_count = 0
    
    for p in paragraphs:
        w_len = len(p.split())
        # Add paragraph to chunk
        current_chunk.append(p)
        word_count += w_len
        
        # If chunk is big enough, seal it
        if word_count >= chunk_size:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
            word_count = 0
            
    # Add any remaining text
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks

def generate_cat_questions(text_chunk):
    if not GEMINI_API_KEY:
        print("No API Key - skipping AI questions")
        return []

    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Generate 3 CAT-style Reading Comprehension questions based on this text.
    Text: {text_chunk[:2000]}...
    
    Strict JSON format:
    [
        {{
            "question": "Question text?",
            "options": ["A", "B", "C", "D"],
            "correct_index": 0,
            "explanation": "Why..."
        }}
    ]
    """
    
    try:
        response = model.generate_content(prompt)
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw_text)
    except Exception as e:
        print(f"AI Error: {e}")
        return []

def main():
    title, paragraphs = scrape_essay(TARGET_URL)
    passages = chunk_text(paragraphs)
    
    data = {
        "metadata": {
            "title": title,
            "source": TARGET_URL,
            "date_scraped": str(datetime.now().date())
        },
        "passages": []
    }
    
    print(f"Processing {len(passages)} passages...")
    
    for i, p_text in enumerate(passages):
        questions = generate_cat_questions(p_text)
        data["passages"].append({
            "id": i + 1,
            "text": p_text,
            "questions": questions
        })
        time.sleep(2) 
        
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)
    print("Done.")

if __name__ == "__main__":
    main()

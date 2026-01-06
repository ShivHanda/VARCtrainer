import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai
from datetime import datetime
import time
import random

# --- CONFIG ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("WARNING: GEMINI_API_KEY is missing. Questions will not be generated.")

# List of URLs to try if the first one fails (Resiliency)
BACKUP_URLS = [
    "https://aeon.co/essays/how-to-be-a-stoic-when-you-don-t-know-how",
    "https://aeon.co/essays/why-the-human-brain-is-not-like-a-computer",
    "https://aeon.co/essays/the-psychology-of-why-we-struggle-with-uncertainty"
]

def get_headers():
    """Returns headers that look like a real Chrome browser."""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://google.com'
    }

def scrape_essay(url):
    print(f"Attempting to scrape: {url}")
    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        response.raise_for_status() # Raises error if status is 404 or 403
    except Exception as e:
        print(f"FAILED to fetch {url}: {e}")
        return None, None

    soup = BeautifulSoup(response.content, 'html.parser')

    # Get Title
    title_tag = soup.find('h1')
    title = title_tag.get_text(strip=True) if title_tag else "Untitled Essay"
    
    # Text Extraction Strategy
    # Aeon's structure is complex. We look for the main article body first.
    article_body = soup.find('div', class_='article__body')
    
    # If standard class not found, try finding the biggest block of text
    if not article_body:
        paragraphs = soup.find_all('p')
    else:
        paragraphs = article_body.find_all('p')

    clean_text = []
    for p in paragraphs:
        text = p.get_text(strip=True)
        # Filter logic: Must be a sentence, not a menu item
        if len(text.split()) > 20 and "subscribe" not in text.lower(): 
            clean_text.append(text)
            
    if not clean_text or len(clean_text) < 3:
        print("WARNING: Scraped text is too short. Likely blocked or wrong page.")
        return None, None

    return title, clean_text

def chunk_text(paragraphs, chunk_size=500):
    chunks = []
    current_chunk = []
    word_count = 0
    
    for p in paragraphs:
        w_len = len(p.split())
        current_chunk.append(p)
        word_count += w_len
        
        if word_count >= chunk_size:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
            word_count = 0
            
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks

def generate_cat_questions(text_chunk):
    if not GEMINI_API_KEY:
        return []

    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Very strict prompt to ensure JSON doesn't break
    prompt = f"""
    You are a CAT (IIM) Exam Setter. Create 3 Reading Comprehension questions for this text.
    
    TEXT:
    {text_chunk[:3000]}
    
    REQUIREMENTS:
    1. Question 1: Inference based.
    2. Question 2: Main Idea / Structure.
    3. Question 3: Detail based (Direct).
    
    OUTPUT FORMAT:
    Return ONLY a raw JSON array. Do NOT use markdown. Do NOT use ```json.
    [
        {{
            "question": "...",
            "options": ["A", "B", "C", "D"],
            "correct_index": 0,
            "explanation": "..."
        }}
    ]
    """
    
    try:
        response = model.generate_content(prompt)
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw_text)
    except Exception as e:
        print(f"AI Generation Error: {e}")
        # Return fallback empty list so site doesn't crash
        return []

def main():
    # 1. Try to find a working URL from our list
    title = None
    paragraphs = None
    
    # Shuffle URLs to get different content sometimes
    targets = BACKUP_URLS.copy()
    random.shuffle(targets)
    
    for url in targets:
        title, paragraphs = scrape_essay(url)
        if paragraphs:
            # We found a working essay!
            current_url = url
            break
            
    if not paragraphs:
        print("CRITICAL ERROR: Could not scrape ANY url. Check network/headers.")
        exit(1) # Fail the GitHub Action

    # 2. Process Content
    passages = chunk_text(paragraphs)
    
    data = {
        "metadata": {
            "title": title,
            "source": current_url,
            "date_scraped": str(datetime.now().date())
        },
        "passages": []
    }
    
    print(f"Successfully scraped '{title}'. Generating questions for {len(passages)} passages...")
    
    # 3. Generate Questions
    for i, p_text in enumerate(passages):
        questions = generate_cat_questions(p_text)
        data["passages"].append({
            "id": i + 1,
            "text": p_text,
            "questions": questions
        })
        time.sleep(2) # Be nice to Gemini API
        
    # 4. Save
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)
    print("Success: data.json updated.")

if __name__ == "__main__":
    main()

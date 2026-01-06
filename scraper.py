import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai
from datetime import datetime
import time
import re

# --- CONFIG ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("CRITICAL ERROR: GEMINI_API_KEY not found.")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def get_latest_essay_from_rss():
    """Fetches the latest essay link from Aeon's RSS Feed."""
    rss_url = "https://aeon.co/feed.rss"
    print(f"Checking RSS Feed: {rss_url}")
    try:
        response = requests.get(rss_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')
        for item in items:
            link = item.link.text
            if "/essays/" in link:
                print(f"Found Essay: {item.title.text}")
                return link, item.title.text
    except Exception as e:
        print(f"RSS Failed: {e}")
    return None, None

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
    """Generates Questions, Tone, and Summary using Gemini."""
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    You are a CAT (Common Admission Test) Exam Setter. Analyze this text.
    
    TEXT:
    {text_chunk[:3500]}
    
    TASK:
    1. Identify the Author's Tone (e.g., Critical, Satirical, Informative).
    2. Write a 1-sentence Summary.
    3. Create 3 Reading Comprehension Questions (Inference, Main Idea, Detail).
    
    OUTPUT FORMAT (Strict JSON):
    {{
        "tone": "One word tone",
        "summary": "One sentence summary",
        "questions": [
            {{
                "question": "...",
                "options": ["A", "B", "C", "D"],
                "correct_index": 0,
                "explanation": "..."
            }}
        ]
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        # Clean Markdown
        clean_text = re.sub(r"```json|```", "", response.text).strip()
        data = json.loads(clean_text)
        return data
    except Exception as e:
        print(f"AI Gen Error: {e}")
        return None

def main():
    url, title = get_latest_essay_from_rss()
    if not url: return

    paragraphs = scrape_text_from_url(url)
    if not paragraphs: return

    # Chunking
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

    final_passages = []
    print(f"Analyzing {len(chunks)} passages...")
    
    for i, chunk in enumerate(chunks):
        print(f"Processing Chunk {i+1}...")
        analysis = generate_analysis_real(chunk)
        
        if not analysis:
            # Fallback structure if AI fails
            analysis = {"tone": "Analytical", "summary": "Analysis unavailable.", "questions": []}

        final_passages.append({
            "id": i+1,
            "text": chunk,
            "tone": analysis.get("tone", "Neutral"),
            "summary": analysis.get("summary", "No summary available."),
            "questions": analysis.get("questions", [])
        })
        time.sleep(4) 

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
    print("Success: Real data generated.")

if __name__ == "__main__":
    main()

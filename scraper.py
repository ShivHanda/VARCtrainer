import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai
from datetime import datetime
import time

# --- CONFIG ---
# GitHub Secret se API Key uthayega
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("Warning: No API Key found. AI questions will be skipped.")

def get_latest_essay_url():
    """Fetches the very first essay link from Aeon's essays page."""
    try:
        url = "https://aeon.co/essays"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Finding the first link that looks like an essay
        # Aeon structure changes, but usually links are inside 'a' tags with specific classes
        # This is a generic finder for the first deep link
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            if '/essays/' in href and href.count('/') == 2: # Basic filter
                return f"https://aeon.co{href}"
    except Exception as e:
        print(f"Error finding latest essay: {e}")
    
    # Fallback if scraping fails
    return "https://aeon.co/essays/how-to-be-a-stoic-when-you-don-t-know-how"

def scrape_essay(url):
    print(f"Scraping: {url}")
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')

    title = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Unknown Title"
    
    article_body = soup.find('div', class_='article__body')
    if not article_body:
        # Fallback 
        paragraphs = [p.get_text() for p in soup.find_all('p')]
    else:
        paragraphs = [p.get_text() for p in article_body.find_all('p')]
        
    # Clean logic: Remove short intro text/captions
    clean_text = [p for p in paragraphs if len(p.split()) > 25]
    return title, clean_text

def chunk_text(paragraphs, chunk_size=600):
    chunks = []
    current_chunk = []
    word_count = 0
    
    for p in paragraphs:
        w_len = len(p.split())
        if word_count + w_len > chunk_size and word_count > 350:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [p]
            word_count = w_len
        else:
            current_chunk.append(p)
            word_count += w_len
            
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks

def generate_cat_questions(text_chunk):
    """Uses Gemini to generate CAT VARC style questions."""
    if not GEMINI_API_KEY:
        return []

    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    You are a CAT (Common Admission Test) Exam Setter. 
    Read the following passage and generate 3 high-quality multiple-choice questions based on it.
    
    Passage:
    {text_chunk}
    
    The questions must be of these specific types:
    1. Inference based (Indirect conclusion)
    2. Main Idea / Theme
    3. Tone of the author OR Structure of argument
    
    Return the output strictly as a JSON array with this format (no markdown, just raw JSON):
    [
        {{
            "question": "Question text here...",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_index": 0,
            "explanation": "Why A is correct..."
        }}
    ]
    """
    
    try:
        response = model.generate_content(prompt)
        # Clean up if AI puts ```json markdown
        cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_text)
    except Exception as e:
        print(f"AI Generation Error: {e}")
        return []

def main():
    url = get_latest_essay_url()
    title, paragraphs = scrape_essay(url)
    passages = chunk_text(paragraphs)
    
    data = {
        "metadata": {
            "title": title,
            "source": url,
            "date_scraped": str(datetime.now().date())
        },
        "passages": []
    }
    
    print(f"Found {len(passages)} passages. Generating questions...")
    
    for i, p_text in enumerate(passages):
        # Generate AI questions for each chunk
        ai_questions = generate_cat_questions(p_text)
        
        data["passages"].append({
            "id": i + 1,
            "text": p_text,
            "questions": ai_questions
        })
        
        # Important: Sleep to avoid hitting API rate limits instantly
        time.sleep(4) 
        
    # Save to JSON
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)
    print("Success: data.json created with AI questions.")

if __name__ == "__main__":
    main()

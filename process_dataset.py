import json
import pandas as pd
import re
import os

CSV_PATH = 'backend/detectors/data/jailbreak_prompts_2023_12_25.csv'
JSON_PATH = 'backend/detectors/data/jailbreak_prompts.json'

df = pd.read_csv(CSV_PATH)

if 'prompt' in df.columns:
    prompts = df['prompt'].dropna().tolist()
else:
    prompts = []

with open(JSON_PATH, 'r', encoding='utf-8') as f:
    existing_data = json.load(f)

existing_texts = {d['text'].strip().lower() for d in existing_data}
new_entries = []

# Template artifact regex (like [INSERT PROMPT HERE], {URL}, [PROMPT], [KEYWORD])
template_regex = re.compile(r'\[[A-Z0-9_\s]+\]|\{[A-Z0-9_\s]+\}')

def categorize(text):
    text_lower = text.lower()
    if 'system prompt' in text_lower or 'hidden instructions' in text_lower:
        return 'system_prompt_extraction'
    elif 'ignore' in text_lower and 'instructions' in text_lower:
        return 'instruction_override'
    elif 'act as' in text_lower or 'pretend to be' in text_lower or 'persona' in text_lower or 'roleplay' in text_lower:
        return 'role_play'
    elif 'data' in text_lower and 'server' in text_lower:
        return 'data_exfiltration'
    else:
        return 'general_jailbreak'

added_count = 0

for p in prompts:
    p_str = str(p).strip()
    if not p_str: continue
    
    # Check length
    words = p_str.split()
    if len(words) > 200:
        continue
        
    # Check for templates
    if template_regex.search(p_str):
        continue
        
    # Deduplicate
    if p_str.lower() in existing_texts:
        continue
        
    existing_texts.add(p_str.lower())
    
    cat = categorize(p_str)
    new_entries.append({
        'text': p_str,
        'category': cat,
        'source': 'verazuo/jailbreak_llms'
    })
    added_count += 1

existing_data.extend(new_entries)

with open(JSON_PATH, 'w', encoding='utf-8') as f:
    json.dump(existing_data, f, indent=4)

print(f"Added {added_count} new phrases. New total: {len(existing_data)}")

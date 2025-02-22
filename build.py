import csv
import json
import os
import sqlite3
import sys
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv('.env')

# Get OpenAI API key from environment variable
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Function to create database tables
def create_tables(conn):
    cursor = conn.cursor()
    
    # Table for lemmas with input part of speech
    cursor.execute('''CREATE TABLE IF NOT EXISTS lemmas (
                        lemma_id INTEGER PRIMARY KEY,
                        lemma TEXT UNIQUE,
                        input_part_of_speech CHAR(1)
                      )''')
    
    # Table for words (including all forms)
    cursor.execute('''CREATE TABLE IF NOT EXISTS words (
                        word_id INTEGER PRIMARY KEY,
                        word TEXT UNIQUE,
                        lemma_id INTEGER,
                        FOREIGN KEY (lemma_id) REFERENCES lemmas (lemma_id)
                      )''')
    
    # Table for entries (parts of speech from API)
    cursor.execute('''CREATE TABLE IF NOT EXISTS entries (
                        entry_id INTEGER PRIMARY KEY,
                        lemma_id INTEGER,
                        part_of_speech CHAR(1),
                        order_index INTEGER,
                        FOREIGN KEY (lemma_id) REFERENCES lemmas (lemma_id)
                      )''')
    
    # Table for definitions
    cursor.execute('''CREATE TABLE IF NOT EXISTS definitions (
                        definition_id INTEGER PRIMARY KEY,
                        entry_id INTEGER,
                        definition TEXT,
                        order_index INTEGER,
                        FOREIGN KEY (entry_id) REFERENCES entries (entry_id)
                      )''')
    
    # Table for synonyms
    cursor.execute('''CREATE TABLE IF NOT EXISTS synonyms (
                        synonym_id INTEGER PRIMARY KEY,
                        entry_id INTEGER,
                        synonym TEXT,
                        order_index INTEGER,
                        FOREIGN KEY (entry_id) REFERENCES entries (entry_id)
                      )''')
    
    # Table for antonyms
    cursor.execute('''CREATE TABLE IF NOT EXISTS antonyms (
                        antonym_id INTEGER PRIMARY KEY,
                        entry_id INTEGER,
                        antonym TEXT,
                        order_index INTEGER,
                        FOREIGN KEY (entry_id) REFERENCES entries (entry_id)
                      )''')
    
    # Create indexes for efficient querying
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lemmas_lemma ON lemmas (lemma)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_words_word ON words (word)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_words_lemma_id ON words (lemma_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entries_lemma_id ON entries (lemma_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_definitions_entry_id ON definitions (entry_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_synonyms_entry_id ON synonyms (entry_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_antonyms_entry_id ON antonyms (entry_id)')
    
    conn.commit()

# Function to insert lemma, its word forms, and entries into the database
def insert_lemma_entries(conn, lemma, input_pos, word_forms, entries):
    cursor = conn.cursor()
    
    # Insert lemma with its input part of speech if not exists
    cursor.execute("INSERT OR IGNORE INTO lemmas (lemma, input_part_of_speech) VALUES (?, ?)", (lemma, input_pos))
    cursor.execute("SELECT lemma_id FROM lemmas WHERE lemma = ?", (lemma,))
    lemma_id = cursor.fetchone()[0]
    
    # Insert word forms
    for word_form in word_forms:
        cursor.execute("INSERT OR IGNORE INTO words (word, lemma_id) VALUES (?, ?)", (word_form, lemma_id))
    
    # Insert each entry (part of speech from API)
    for entry_index, entry in enumerate(entries):
        part_of_speech = entry['part_of_speech']
        cursor.execute('''INSERT INTO entries (lemma_id, part_of_speech, order_index)
                          VALUES (?, ?, ?)''', (lemma_id, part_of_speech, entry_index))
        entry_id = cursor.lastrowid
        
        # Insert definitions
        for def_index, definition in enumerate(entry['definitions']):
            cursor.execute('''INSERT INTO definitions (entry_id, definition, order_index)
                              VALUES (?, ?, ?)''', (entry_id, definition, def_index))
        
        # Insert synonyms
        for syn_index, synonym in enumerate(entry['synonyms']):
            cursor.execute('''INSERT INTO synonyms (entry_id, synonym, order_index)
                              VALUES (?, ?, ?)''', (entry_id, synonym, syn_index))
        
        # Insert antonyms
        for ant_index, antonym in enumerate(entry['antonyms']):
            cursor.execute('''INSERT INTO antonyms (entry_id, antonym, order_index)
                              VALUES (?, ?, ?)''', (entry_id, antonym, ant_index))
    
    conn.commit()

# New helper: Build prompt for a lemma
def build_prompt(lemma, input_pos):
    prompt = f'''Provide the word forms, definitions, synonyms, and antonyms for the lemma "{lemma}" with its primary part of speech code "{input_pos}". Use these one-letter codes for parts of speech:
a: article
c: conjunction
d: determiner
e: existential there
i: preposition
j: adjective
m: number
n: noun
p: pronoun
r: adverb
t: infinitive marker
u: interjection
v: verb
x: not

For definition, use sentence fragments, not full sentences.
Synonyms and antonyms should be single words or short phrases.

Format the response as a JSON object with the following schema:
{{
  "lemma": "string",
  "word_forms": ["string", ...],
  "entries": [
    {{
      "part_of_speech": "single-letter-code",
      "definitions": ["string", ...],
      "synonyms": ["string", ...],
      "antonyms": ["string", ...]
    }},
    ...
  ]
}}
Include all inflected forms of the lemma in "word_forms" (e.g., for "run": "run", "runs", "running", "ran"). Ensure parts of speech are ordered by common usage, prioritizing "{input_pos}" if applicable, and within each part of speech, definitions, synonyms, and antonyms are ordered by common usage.'''
    return prompt

# New function: submit batch job
def submit_batch():
    # Read the TSV input file
    try:
        with open('lemmas.tsv', 'r', newline='') as file:
            reader = csv.reader(file, delimiter='\t')
            next(reader)  # Skip header
            lemma_pos_pairs = [(row[0].strip().lower(), row[1].strip().lower()) for row in reader if len(row) >= 2]
    except FileNotFoundError:
        print("Error: 'lemmas.tsv' not found.")
        sys.exit(1)
    
    tasks = []
    for idx, (lemma, input_pos) in enumerate(lemma_pos_pairs):
        prompt = build_prompt(lemma, input_pos)
        task = {
            "custom_id": f"task-{idx}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "gpt-4o-mini",
                "temperature": 0,
                "response_format": { "type": "json_object" },
                "messages": [
                    { "role": "system", "content": "You are a helpful assistant that provides word forms, definitions, synonyms, and antonyms in JSON format." },
                    { "role": "user", "content": prompt }
                ]
            }
        }
        tasks.append(task)
    
    # Write batch tasks file
    tasks_file = "batch_tasks_lemmas.jsonl"
    with open(tasks_file, 'w') as file:
        for task in tasks:
            file.write(json.dumps(task) + "\n")
    print(f"Batch tasks file created: {tasks_file}")
    
    # Upload file and create batch job
    batch_file = client.files.create(
        file=open(tasks_file, "rb"),
        purpose="batch"
    )
    batch_job = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h"
    )
    # Save job ID for processing later
    with open("batch_job_id.txt", "w") as f:
        f.write(batch_job.id)
    print(f"Batch job submitted. Job ID: {batch_job.id}")

# New function: process batch job results and update the database
def process_batch():
    # Read job ID from file
    try:
        with open("batch_job_id.txt", "r") as f:
            job_id = f.read().strip()
    except FileNotFoundError:
        print("No batch job ID found. Please run 'submit' command first.")
        sys.exit(1)
    
    # Retrieve batch job
    batch_job = client.batches.retrieve(job_id)
    if batch_job.status != "completed":
        print(f"Batch job not complete yet. Current status: {batch_job.status}")
        sys.exit(0)
    
    # Download results
    result_file_id = batch_job.output_file_id
    result_content = client.files.content(result_file_id).content
    results_file = "batch_job_results_lemmas.jsonl"
    with open(results_file, "wb") as file:
        file.write(result_content)
    print(f"Results saved to: {results_file}")
    
    # Re-read lemmas.tsv to match tasks with input
    try:
        with open('lemmas.tsv', 'r', newline='') as file:
            reader = csv.reader(file, delimiter='\t')
            next(reader)
            lemma_pos_pairs = [(row[0].strip().lower(), row[1].strip().lower()) for row in reader if len(row) >= 2]
    except FileNotFoundError:
        print("Error: 'lemmas.tsv' not found.")
        sys.exit(1)
    
    # Connect to SQLite database
    conn = sqlite3.connect('dictionary.db')
    create_tables(conn)
    
    # Process each result (custom_id is task-{idx} so idx maps to lemma_pos_pairs)
    with open(results_file, "r") as file:
        for line in file:
            try:
                obj = json.loads(line.strip())
                task_id = obj.get("custom_id", "")
                idx = int(task_id.split("-")[-1])
                # Get the API response contained in response.body.choices[0].message.content
                api_resp = obj["response"]["body"]["choices"][0]["message"]["content"]
                data = json.loads(api_resp)
                
                lemma, input_pos = lemma_pos_pairs[idx]
                if data.get("lemma", "").lower() != lemma:
                    print(f"Warning: Response lemma '{data.get('lemma')}' does not match input '{lemma}'")
                    continue
                insert_lemma_entries(conn, lemma, input_pos, data.get("word_forms", []), data.get("entries", []))
                print(f"Processed: {lemma} ({input_pos})")
            except Exception as e:
                print(f"Error processing result for task {task_id}: {e}")
    conn.close()
    print("Dictionary and thesaurus build complete.")

# Main execution: check command-line argument to choose mode.
def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("submit", "process"):
        print("Usage: python build.py [submit|process]")
        sys.exit(1)
    command = sys.argv[1]
    if command == "submit":
        submit_batch()
    elif command == "process":
        process_batch()

if __name__ == "__main__":
    main()

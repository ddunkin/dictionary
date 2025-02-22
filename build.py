import csv
import json
import os
import sqlite3
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

# Function to fetch data from OpenAI API
def get_lemma_data(lemma, input_pos):
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
    response = client.chat.completions.create(model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful assistant that provides word forms, definitions, synonyms, and antonyms in JSON format."},
        {"role": "user", "content": prompt}
    ],
    temperature=0,
    response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

# Main execution
def main():
    # Connect to SQLite database
    conn = sqlite3.connect('dictionary.db')
    create_tables(conn)
    
    # Read the TSV input file
    try:
        with open('lemmas.tsv', 'r', newline='') as file:
            reader = csv.reader(file, delimiter='\t')
            next(reader)  # Skip header row
            lemma_pos_pairs = [(row[0].strip().lower(), row[1].strip().lower()) for row in reader if len(row) >= 2]
    except FileNotFoundError:
        print("Error: 'lemmas.tsv' not found. Please create this file with 'lemma<TAB>part_of_speech' per line and a header.")
        conn.close()
        return
    
    print(f"Processing {len(lemma_pos_pairs)} lemmas...")
    
    # Process each lemma and its part of speech
    for lemma, input_pos in lemma_pos_pairs:
        try:
            data = get_lemma_data(lemma, input_pos)
            if data['lemma'].lower() != lemma:
                print(f"Warning: Response lemma '{data['lemma']}' does not match input '{lemma}'")
                continue
            insert_lemma_entries(conn, lemma, input_pos, data['word_forms'], data['entries'])
            print(f"Processed: {lemma} ({input_pos})")
        except Exception as e:
            print(f"Error processing '{lemma} ({input_pos})': {e}")
    
    conn.close()
    print("Dictionary and thesaurus build complete.")

if __name__ == "__main__":
    main()

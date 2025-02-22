# Dictionary and Thesaurus Builder

This project creates a free English dictionary and thesaurus using an LLM. It fetches word forms, definitions, synonyms, and antonyms for given lemmas and stores them in a SQLite database.

## Project Structure

- `build.py`: Main script to build the dictionary and thesaurus.
- `lemmas.tsv`: Input file containing lemmas and their parts of speech.
- `.env`: Environment file containing the OpenAI API key.

## Setup

1. **Create a virtual environment and install dependencies:**

   ```sh
   uv venv
   uv pip install -r requirements.txt
   ```

2. **Set up the environment variables:**

   - Create a `.env` file in the project root with the following content:
     ```
     OPENAI_API_KEY=your_openai_api_key
     ```

3. **Prepare the input file:**
   - Create a `lemmas.tsv` file with the following format:
     ```
     lemma    part_of_speech
     run      v
     happy    j
     ```

## Usage

1. **Run the script to build the dictionary and thesaurus:**

   ```sh
   uv run build.py
   ```

2. **Check the output:**
   - The script will create a `dictionary.db` SQLite database with the fetched data.

## Notes

- The script processes the first 100 lemmas from the `lemmas.tsv` file.
- Ensure the parts of speech are provided using the following one-letter codes:
  - `a`: article
  - `c`: conjunction
  - `d`: determiner
  - `e`: existential there
  - `i`: preposition
  - `j`: adjective
  - `m`: number
  - `n`: noun
  - `p`: pronoun
  - `r`: adverb
  - `t`: infinitive marker
  - `u`: interjection
  - `v`: verb
  - `x`: not

## License

This project is licensed under the MIT License.

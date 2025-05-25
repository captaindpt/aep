import pathlib
import yaml
import re

# This script assumes it is run from the root of the 'aep-sdk' directory.
DOCS_DIR = pathlib.Path("docs")
QA_OUTPUT_FILE = pathlib.Path("qa/qa.yaml")

def main():
    if not DOCS_DIR.exists() or not DOCS_DIR.is_dir():
        print(f"Error: Docs directory not found at '{DOCS_DIR.resolve()}'")
        print("Please ensure the script is run from the 'aep-sdk' root and 'docs/' exists.")
        return

    doc_files = list(DOCS_DIR.rglob("*.md*")) # Handles .md and .mdx
    if not doc_files:
        print(f"No markdown files found in '{DOCS_DIR.resolve()}'")
        return

    print(f"Found {len(doc_files)} markdown files in '{DOCS_DIR.resolve()}'. Generating QA pairs...")
    qa_items = []
    seen_questions = set() # For deduplication

    for idx, p in enumerate(doc_files):
        # Filter out READMEs and _index files
        if p.name.lower().startswith(("readme", "_index")):
            print(f"Skipping non-content file: {p.name}")
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"^#\s+(.+?)(?:\n|$)", txt, re.MULTILINE)
            if not m:
                fm_title_match = re.search(r"title:\s*(?:\'|\")(.+?)(?:\'|\")", txt, re.IGNORECASE | re.MULTILINE)
                if fm_title_match:
                    title_text = fm_title_match.group(1).strip()
                else:
                    title_text = p.stem.replace("_", " ").replace("-", " ").capitalize()
            else:
                title_text = m.group(1).strip()
            
            title_text_clean = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', title_text)
            title_text_clean = re.sub(r'`([^`]+)`', r'\1', title_text_clean)
            title_text_clean = title_text_clean.strip("*")

            question = f"What is {title_text_clean}?"

            if question in seen_questions:
                print(f"Skipping duplicate question for title '{title_text_clean}' from file {p.name}")
                continue
            seen_questions.add(question)
            
            first_word = title_text_clean.split(' ')[0].lower()
            first_word_clean = re.sub(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$', '', first_word)

            qa_item = dict(
                id=f"Q{idx:03}", # Note: idx might not be dense due to skipping files/questions
                question=question,
                expected_answer_keywords=[first_word_clean] if first_word_clean else ["topic"],
                golden_doc_sources=[str(p.relative_to(DOCS_DIR))], # Path relative to DOCS_DIR
                category="Auto-generated",
                difficulty="Medium", 
            )
            qa_items.append(qa_item)
        except Exception as e:
            print(f"Could not process file {p}: {e}")

    QA_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QA_OUTPUT_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(qa_items, f, sort_keys=False, allow_unicode=True)
    
    print(f"Generated {len(qa_items)} Q/A pairs into '{QA_OUTPUT_FILE.resolve()}'")
    print("Please review and curate this file, aiming for ~100 high-quality questions.")

if __name__ == "__main__":
    main()

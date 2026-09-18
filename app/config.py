from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CSV_PATH = PROJECT_ROOT /  "data" / "support_tickets.csv"
DB_PATH = PROJECT_ROOT / "app" / "db" / "support_tickets.db"


print(PROJECT_ROOT)
print(CSV_PATH)
print(DB_PATH)


PROMPTS_DIR = PROJECT_ROOT / "app" / "llm" / "prompts"

GENERATE_SQL_PROMPT_TEXT = Path(
    PROMPTS_DIR / "generate_sql_prompt.txt"
).read_text(encoding="utf-8")

FORMAT_SQL_PROMPT_TEXT = Path(
    PROMPTS_DIR / "format_sql_prompt.txt"
).read_text(encoding="utf-8")

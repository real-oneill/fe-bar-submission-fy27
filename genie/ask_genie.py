"""Ask the Genie space the evaluation questions through the Conversation API and commit the answers as text.

  uv run --with databricks-sdk python genie/ask_genie.py --profile fevm-evan-aws-01

Writes genie/genie_answers.md: per question, Genie's text answer, the SQL it generated and the result rows.
"""
import argparse, datetime as dt, pathlib, time
from databricks.sdk import WorkspaceClient

ap = argparse.ArgumentParser()
ap.add_argument("--profile", required=True)
ap.add_argument("--space-id", default=(pathlib.Path(__file__).with_name("space_id.txt").read_text().strip()
                                       if pathlib.Path(__file__).with_name("space_id.txt").exists() else ""))
a = ap.parse_args()
w = WorkspaceClient(profile=a.profile)
QUESTIONS = [
    "How many FTE does the pipeline save, and how many FTE are needed today vs with the pipeline?",
    "Show FTE saved by document type",
    "How many FTE are saved in each region?",
    "Which region has the lowest line accuracy, and what is its review rate?",
    "How does line accuracy change with document complexity?",
    "Which 5 problem types have the lowest line accuracy?",
    "Which documents were wrong but not routed to review?",
    "How many orders are in the review queue by status and region?",
]


def md_table(cols, rows):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join("" if v is None else str(v).replace("|", "\\|") for v in r) + " |" for r in rows]
    return "\n".join(out)


out = [f"# Genie space answers (collected {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M UTC})", "",
       f"Space `{a.space_id}` on {w.config.host}: {w.config.host}/genie/rooms/{a.space_id}", "",
       "Each question was sent to the space through the Genie Conversation API; below is Genie's own answer, the SQL it",
       "wrote and the rows that SQL returned.", ""]
for q in QUESTIONS:
    print("Q:", q)
    msg = w.genie.start_conversation_and_wait(a.space_id, q)
    out += [f"## Q: {q}", "", f"status: `{msg.status.value if msg.status else ''}`", ""]
    for att in msg.attachments or []:
        if att.text and att.text.content:
            out += ["**Genie:** " + att.text.content.strip(), ""]
        if att.query:
            out += ["```sql", (att.query.query or "").strip(), "```", ""]
            if att.query.description:
                out += [f"_{att.query.description.strip()}_", ""]
            res = w.genie.get_message_attachment_query_result(a.space_id, msg.conversation_id, msg.message_id, att.attachment_id)
            sr = res.statement_response
            if sr and sr.manifest and sr.result:
                cols = [c.name for c in sr.manifest.schema.columns]
                rows = sr.result.data_array or []
                out += [md_table(cols, rows[:30]), "", f"({len(rows)} rows)", ""]
    time.sleep(2)
pathlib.Path(__file__).with_name("genie_answers.md").write_text("\n".join(out) + "\n")
print("wrote genie/genie_answers.md")

# Temporal Ambiguity Study

**Does an interface that is a little unclear about what it wants change how you experience time? A within-subject user study comparing a "directive" prototype with an "ambiguous" one.**

## The idea
Most interfaces are designed to be clear and directive. This study asks what happens when they aren't: does ambiguity make time feel slower or faster, and does it change people's sense of control and calm? Each participant tries **both** versions, so differences come from the design, not from different people.

## How it works
1. **Consent and baseline**: recent sense of time, today's mood
2. **Two sessions, ~2 minutes each**: Figma prototypes embedded in the app (directive and ambiguous), in counterbalanced or random order
3. **Questionnaire after each session**:
   - 7-point scales on time flow, control, predictability, sync with the system and calm
   - metaphor choices, e.g. *time felt like a line / a circle / a loop / a void*; *who was leading: me, the interface, both, nobody*
   - open questions about how their sense of time changed
4. **Short demographics**, then everything is written to Google Sheets as one row per participant

## What's in this repo
| Path | What it is |
|---|---|
| `app.py` | Streamlit study app (consent → baseline → sessions → questionnaires) |
| `config.py` | Prototype links and session length |

## Status
Used for data collection.

## Run it
```bash
pip install -r requirements.txt
streamlit run app.py
```
Needs a `gcp_service_account` entry in Streamlit secrets for Google Sheets.

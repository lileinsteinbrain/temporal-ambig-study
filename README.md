# Temporal Ambiguity Study

## What this is
A Streamlit app for a within-subject user study comparing two interaction prototypes: a **directive** interface and an **ambiguous** one. It asks how ambiguity changes people's experience of time and control.

## Input
- Consent and a short baseline (recent mood and today's state)
- Two Figma prototype sessions (directive and ambiguous), about 120 s each, in a chosen or randomised order
- A questionnaire after each session: 7-point scales plus metaphor questions (texture of the experience, shape of time, who was in control)
- Short demographics

## Processing
- Counterbalances condition order
- Times each session and attaches the condition label to every response

## Output
- Responses stored in Google Sheets for within-subject comparison

## Run it
```bash
pip install -r requirements.txt
streamlit run app.py
```
Prototype URLs and session length are set in `config.py`. Google Sheets logging needs a `gcp_service_account` entry in Streamlit secrets.

"""
The conversation layer — and ONLY the conversation layer. Everything in
this file either (a) turns the patient's free text into structured
(fact, intensity) pairs the reasoning engine can use, or (b) turns the
engine's raw question into something that reads like a doctor said it.

Nothing here decides a disease, a question order, or a confidence
score — reasoning_engine.pl owns all of that. This file is not allowed
to make a diagnosis, and every prompt below says so explicitly.

Uses a local Ollama model (default: llama3.1:8b) — no API key, no
network egress, free. Every call degrades to a safe deterministic
fallback if Ollama is unreachable, so the app never breaks because the
model is unavailable.
"""

import json
import os
import re
import urllib.request
import urllib.error

OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
MODEL = os.environ.get('LLM_MODEL', 'llama3.1:8b')
TIMEOUT = 20


def _call_ollama(prompt):
    data = json.dumps({'model': MODEL, 'prompt': prompt, 'stream': False}).encode()
    req = urllib.request.Request(f'{OLLAMA_HOST}/api/generate', data=data,
                                  headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())['response']
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError):
        return None


EXTRACT_PROMPT = """You are listening to a patient describe how they feel, the way a \
doctor's intake assistant would. Your ONLY job is to identify which of these exact \
symptom codes they mentioned or clearly implied, and how intensely (1 mild, 5 severe) \
they described each one, IF they actually gave any indication of severity.

Valid symptom codes: {codes}

Patient said: "{text}"

Rules:
- Only use codes from the list above. Never invent a new one.
- If they explicitly deny a symptom ("no fever"), do not include it.
- If more than one code could reasonably describe the same thing they
  said (e.g. a general code like "fever" and a more specific one like
  "fever_with_nausea"), include ALL of the codes that apply — do not
  pick just one and drop the others.
- If the patient's wording gives a real clue to how severe/intense it is
  ("pretty bad", "mild", "unbearable", "a little"), set "intensity" to a
  number 1-5. If they gave NO such clue at all, set "intensity" to null
  — do not guess a number. Being honest about "not stated" matters here.
- Respond with ONLY a JSON array like [{{"fact": "fatigue", "intensity": 3}}, \
{{"fact": "cough", "intensity": null}}]. If nothing matches, respond with []. \
No other text.
"""


def _max_plausible_facts(text):
    """
    A cheap, deterministic cap on how many DISTINCT symptoms a message
    could plausibly contain, based on how many list-like separators it
    actually has. A short, single-clause message like "having stomach
    pain" has zero separators and should never yield more than one fact
    — but the model has been observed returning 3-4 completely unrelated
    facts from exactly that kind of input anyway (e.g. inventing
    "chest_pain", "nausea", "vomiting" from a sentence that only said
    "stomach pain"). This doesn't fix the model's accuracy, it just
    puts a hard, text-grounded ceiling on how much damage a single bad
    call can do — results beyond the cap are dropped rather than trusted.
    """
    seps = len(re.findall(r'\band\b|,|\balso\b|\bplus\b|\bas well\b', text.lower()))
    return max(1, seps + 1)


def extract_facts(text, known_fact_codes):
    """
    Returns a list of {"fact": str, "intensity": int, "stated": bool} dicts
    for symptoms recognized in free text, grounded strictly to
    known_fact_codes. "stated" is False when the patient gave no real
    indication of severity and intensity was defaulted to 3 — callers
    should surface that honestly rather than silently assuming "moderate"
    without ever telling the patient. Returns [] (not None) on any
    failure — callers should treat that the same as "nothing recognized."

    The result is capped at _max_plausible_facts(text) entries — see that
    function's docstring for why this matters; this is a real, observed
    failure mode, not a theoretical one.
    """
    prompt = EXTRACT_PROMPT.format(codes=', '.join(sorted(known_fact_codes)),
                                    text=text.replace('"', "'"))
    raw = _call_ollama(prompt)
    if not raw:
        return []
    start, end = raw.find('['), raw.rfind(']')
    if start == -1 or end == -1 or end < start:
        return []
    try:
        parsed = json.loads(raw[start:end + 1])
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    out = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        fact = item.get('fact')
        if fact not in known_fact_codes:
            continue
        raw_intensity = item.get('intensity')
        if raw_intensity is None:
            out.append({'fact': fact, 'intensity': 3, 'stated': False})
        else:
            try:
                intensity = max(1, min(5, int(raw_intensity)))
                out.append({'fact': fact, 'intensity': intensity, 'stated': True})
            except (TypeError, ValueError):
                out.append({'fact': fact, 'intensity': 3, 'stated': False})
    return out[:_max_plausible_facts(text)]


PENDING_ANSWER_PROMPT = """A patient was just asked this exact screening question:
"{question}"

They replied: "{message}"

Does their reply answer THIS question with yes or no, even indirectly or by \
referring back to something they already said (e.g. "I already told you", \
"like I said", "yeah I mentioned that")? Treat a reference back to an earlier \
statement as a genuine "yes" if the context makes clear they are confirming it \
again, not dodging the question.

If yes, and their wording gives any real clue to severity/intensity (1 mild \
to 5 severe), include it; otherwise use null.

Respond with ONLY this JSON, nothing else:
{{"answer": "yes", "intensity": 3}}
or
{{"answer": "no"}}
or
{{"answer": "unclear"}}
"""


def interpret_pending_answer(message, pending_question):
    """
    Grounded check for whether `message` answers `pending_question`
    specifically — unlike extract_facts, this call is told exactly what
    was asked, so it correctly handles a patient referring back to
    something already said ("I already told you I have a fever") instead
    of requiring them to restate it in fresh, extractable wording.
    Returns {"answer": "yes"|"no"|"unclear", "intensity": int|None}.
    Returns {"answer": "unclear", "intensity": None} on any failure.
    """
    prompt = PENDING_ANSWER_PROMPT.format(question=pending_question or '',
                                           message=message.replace('"', "'"))
    raw = _call_ollama(prompt)
    fallback = {'answer': 'unclear', 'intensity': None}
    if not raw:
        return fallback
    start, end = raw.find('{'), raw.rfind('}')
    if start == -1 or end == -1 or end < start:
        return fallback
    try:
        parsed = json.loads(raw[start:end + 1])
    except (ValueError, TypeError):
        return fallback
    if not isinstance(parsed, dict) or parsed.get('answer') not in ('yes', 'no', 'unclear'):
        return fallback
    intensity = parsed.get('intensity')
    if intensity is not None:
        try:
            intensity = max(1, min(5, int(intensity)))
        except (TypeError, ValueError):
            intensity = None
    return {'answer': parsed['answer'], 'intensity': intensity}


SEVERITY_WORDS = {
    'mild': 2, 'minor': 2, 'slight': 2, 'light': 2, 'a little': 2, 'a bit': 2,
    'moderate': 3, 'medium': 3, 'ok': 3, 'okay': 3, 'manageable': 3,
    'bad': 4, 'pretty bad': 4, 'quite bad': 4, 'significant': 4, 'strong': 4,
    'severe': 5, 'very bad': 5, 'extreme': 5, 'awful': 5, 'unbearable': 5, 'terrible': 5,
}


def parse_severity(text):
    """
    Returns an int 1-5 if the message plainly states a severity, or None
    if it doesn't (callers should re-ask once on None, never guess).
    Tries a bare number first (fast, free, no model call), then falls
    back to matching common severity words.
    """
    tl = text.strip().lower()
    m = re.search(r'\b([1-5])\b', tl)
    if m:
        return int(m.group(1))
    for phrase, val in SEVERITY_WORDS.items():
        if phrase in tl:
            return val
    return None


PHRASE_PROMPT = """You are a warm, attentive doctor talking with a patient. You need to \
ask them this exact clinical question, but in your own natural words — the way a real \
doctor speaks in conversation, not reading off a form. Keep the same medical meaning \
exactly; do not loosen or change what is being asked, and do not add any new question, \
reassurance about results, or diagnosis.

Clinical question to ask: "{question}"
{lead_in}

Respond with ONLY the one or two sentences you would actually say. Nothing else.
"""


def phrase_question(question, lead_in=''):
    """
    Returns a natural-language rendering of a fixed clinical question.
    Falls back to the raw question text unchanged if the model is
    unavailable — the engine's question is always asked one way or
    another, phrasing is a comfort layer, never a dependency.
    """
    prompt = PHRASE_PROMPT.format(question=question, lead_in=lead_in)
    raw = _call_ollama(prompt)
    if not raw:
        return question
    cleaned = raw.strip().strip('"')
    return cleaned if cleaned else question


CLARIFY_PROMPT = """A patient was just asked this screening question by a doctor:
"{question}"

Instead of answering, they wrote: "{message}"

If this is a genuine question asking what a term means or why it's being asked, answer \
briefly and plainly (2-3 sentences), like a doctor reassuring a patient — never diagnose \
or hint at what their answer should be. Do not repeat the original question yourself, it \
will be shown again automatically after your answer.

If this is NOT a genuine clarifying question (a typo, a vague or partial attempt to \
answer, gibberish, anything off-topic) respond with exactly: NOT_A_QUESTION

Respond with ONLY your answer, or exactly NOT_A_QUESTION."""

QUESTION_STARTERS = ('what', 'why', 'how', 'when', 'where', 'who', 'which',
                     'is ', 'are ', 'does ', 'do ', 'can ', 'could ', 'should ')


def looks_like_question(text):
    tl = text.strip().lower()
    return '?' in tl or tl.startswith(QUESTION_STARTERS)


EXPLAIN_FACT_PROMPT = """A patient is being asked to rate how severe this symptom is for \
them: "{fact_label}" (the actual question they were asked: "{question}").

Instead of giving a rating, they asked: "{message}"

Answer their question clearly and briefly (2-3 sentences), like a doctor would, in plain \
language. Do not diagnose or suggest what their rating should be. Do not repeat the \
original question yourself, it will be shown again automatically after your answer."""


def explain_fact(message, fact_label, question):
    """
    Answers a genuine clarifying question asked DURING the severity-rating
    step (e.g. "what is fatigue?" instead of a 1-5 number). Returns None
    if the message isn't a real question, or the model is unavailable —
    callers fall back to the generic "give me a number" re-prompt on None.
    """
    if not looks_like_question(message):
        return None
    prompt = EXPLAIN_FACT_PROMPT.format(fact_label=fact_label, question=question or '',
                                         message=message.replace('"', "'"))
    raw = _call_ollama(prompt)
    return raw.strip() if raw else None


def clarify(message, pending_question):
    """
    Returns a plain-language answer to a genuine clarifying question, or
    None if the message isn't one (or the model is unavailable) — callers
    fall back to a generic re-prompt on None. Never invoked at all unless
    looks_like_question() already passed, so vague non-question replies
    never reach the model in the first place.
    """
    if not looks_like_question(message):
        return None
    prompt = CLARIFY_PROMPT.format(question=pending_question or '', message=message.replace('"', "'"))
    raw = _call_ollama(prompt)
    if not raw:
        return None
    raw = raw.strip()
    if not raw or raw.upper().lstrip('.').startswith('NOT_A_QUESTION'):
        return None
    return raw

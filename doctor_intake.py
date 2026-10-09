"""
Doctor-side knowledge acquisition — a guided, deterministic conversation
(no LLM required, same philosophy as the patient-side keyword fallback)
that lets a doctor describe a new condition in plain language and, only
after they explicitly confirm it, commits it into doctor_knowledge.yaml
— the SAME production-rule file the reasoning engine reads from, kept
completely separate from patient_strategy.yaml (the conversation-strategy
rules). Nothing here ever touches the strategy file.

Nothing is added automatically just because a doctor is testing things
out — the draft is only committed on an explicit confirm step.
"""

import re
import os

import yaml

import generate_rules

BASE = os.path.dirname(os.path.abspath(__file__))
DOCTOR_YAML = os.path.join(BASE, 'doctor_knowledge.yaml')
PATIENT_YAML = os.path.join(BASE, 'patient_strategy.yaml')


def slugify(text):
    s = re.sub(r'[^a-z0-9]+', '_', text.strip().lower())
    return s.strip('_')


def new_session():
    return {
        'stage': 'name',
        'name': None, 'category': None, 'threshold': None,
        'symptoms': [],
        'cur_question': None, 'cur_fact': None, 'cur_severity': None,
    }


def start_message():
    return ("Rule Intake — let's add a new condition to the knowledge base.\n\n"
            "What condition would you like to add? (e.g. \"Migraine\")")


def step(session, message):
    """Advances the guided intake by one turn. Returns (reply, session,
    draft_or_None) — draft is only non-None once review is reached."""
    stage = session['stage']
    msg = message.strip()

    if stage == 'name':
        session['name'] = slugify(msg)
        session['stage'] = 'symptom_question'
        return (f"Got it — **{msg.strip().title()}**.\n\n"
                "Describe the first confirming question, the way you'd ask the patient "
                "(e.g. \"Do you have a throbbing, one-sided headache?\")", session, None)

    if stage == 'symptom_question':
        session['cur_question'] = msg
        session['stage'] = 'symptom_fact'
        suggested = slugify(msg.split('?')[0])[:40] or 'symptom'
        session['cur_fact'] = suggested
        return (f"What should this be called internally? (a short code, e.g. "
                f"\"{suggested}\" — press enter to use that, or type your own)", session, None)

    if stage == 'symptom_fact':
        if msg:
            slug = slugify(msg)
            if not slug:
                return (f"That didn't give me a usable short code. Please use letters, "
                         f"numbers, or spaces — or press enter to use \"{session['cur_fact']}\".",
                         session, None)
            session['cur_fact'] = slug
        existing = {s['fact'] for s in session['symptoms']}
        if session['cur_fact'] in existing:
            i = 2
            while f"{session['cur_fact']}_{i}" in existing:
                i += 1
            session['cur_fact'] = f"{session['cur_fact']}_{i}"
        session['stage'] = 'symptom_severity'
        return ("On a scale of 1 (mild/nonspecific) to 5 (severe/hallmark), how clinically "
                "significant is this symptom on its own?", session, None)

    if stage == 'symptom_severity':
        digits = re.sub(r'[^0-9]', '', msg)
        sev = max(1, min(5, int(digits))) if digits else 3
        session['cur_severity'] = sev
        session['stage'] = 'symptom_hallmark'
        return (f"Severity {sev}/5 noted.\n\n"
                "Is this a *hallmark* symptom — specific enough that confirming it alone "
                "should be enough to confirm the condition? (yes/no)", session, None)

    if stage == 'symptom_hallmark':
        tl = msg.strip().lower()
        if tl in ('y', 'yes', 'yeah', 'yep', 'correct', 'true'):
            hallmark = True
        elif tl in ('n', 'no', 'nope', 'false'):
            hallmark = False
        else:
            return ("Just to be clear — should this symptom be enough on its own to confirm "
                     "the condition? Please answer yes or no.", session, None)
        session['symptoms'].append({
            'fact': session['cur_fact'], 'question': session['cur_question'],
            'severity': session['cur_severity'], 'hallmark': hallmark,
        })
        session['cur_question'] = session['cur_fact'] = session['cur_severity'] = None
        session['stage'] = 'symptom_more'
        return ("Added. Describe another confirming question, or type \"done\" if that's "
                "all of them.", session, None)

    if stage == 'symptom_more':
        if msg.lower() in ('done', 'no', 'no more', "that's all", 'finished'):
            session['stage'] = 'threshold'
            n = len(session['symptoms'])
            return (f"{n} symptom{'s' if n != 1 else ''} captured.\n\n"
                     "What confidence percentage (0-100) should be required to confirm this "
                     "condition when no hallmark fact fires? (e.g. 60)", session, None)
        session['cur_question'] = msg
        session['stage'] = 'symptom_fact'
        suggested = slugify(msg.split('?')[0])[:40] or 'symptom'
        session['cur_fact'] = suggested
        return (f"What should this be called internally? (a short code, e.g. "
                f"\"{suggested}\" — press enter to use that, or type your own)", session, None)

    if stage == 'threshold':
        digits = re.sub(r'[^0-9]', '', msg)
        session['threshold'] = max(1, min(100, int(digits))) if digits else 60
        session['stage'] = 'category'
        return ("Last question — what broad category does this condition belong to? "
                "(e.g. \"respiratory\", \"metabolic\", \"neurological\")", session, None)

    if stage == 'category':
        session['category'] = slugify(msg) or 'other'
        session['stage'] = 'review'
        return ("Here's the draft — review it below and confirm to add it to the knowledge "
                "base, or discard it.", session, build_draft(session))

    if stage == 'review':
        return ("Please use Confirm or Discard on the draft above.", session, build_draft(session))

    return ("This intake is finished.", session, None)


def build_draft(session):
    return {
        'name': session['name'], 'category': session['category'],
        'threshold': session['threshold'], 'symptoms': session['symptoms'],
    }


def _escape(text):
    return text.replace('"', '\\"')


def _disease_block_text(draft):
    lines = [f"\n  {draft['name']}:",
             f"    category: {draft['category']}",
             f"    threshold: {draft['threshold']}",
             f"    symptoms:"]
    for s in draft['symptoms']:
        lines.append(f"      - fact: {s['fact']}")
        lines.append(f"        question: \"{_escape(s['question'])}\"")
        lines.append(f"        severity: {s['severity']}")
        if s['hallmark']:
            lines.append(f"        hallmark: true")
    return '\n'.join(lines) + '\n'


def commit_draft(draft):
    """
    Writes the confirmed draft into doctor_knowledge.yaml (the doctor
    production-rule file — never patient_strategy.yaml) via targeted
    text insertion, NOT a full YAML re-dump — a re-dump would silently
    discard every hand-written comment explaining the file's format.
    Regenerates both compiled Prolog rule files afterward. Raises
    ValueError if the condition already exists.
    """
    with open(DOCTOR_YAML) as f:
        text = f.read()
    config = yaml.safe_load(text)

    name = draft['name']
    if name in config['diseases']:
        raise ValueError(f'A condition named "{name}" already exists.')

    # Doctor's file always ends with the last disease's own content, so
    # appending at the very end is always a safe insertion point.
    text = text.rstrip('\n') + '\n' + _disease_block_text(draft)
    yaml.safe_load(text)  # validate before writing anything to disk
    with open(DOCTOR_YAML, 'w') as f:
        f.write(text)

    # New facts this condition introduces should also be recognizable by
    # the patient-side recognizer as opening symptoms — route each new
    # fact to at least this condition. Inserted right after the
    # "symptom_routing:" key specifically (not appended at file end,
    # since a later section — category_intro — follows it and a
    # misplaced same-indent line would silently corrupt that instead).
    with open(PATIENT_YAML) as f:
        patient_text = f.read()
    new_lines = []
    for s in draft['symptoms']:
        fact = s['fact']
        m = re.search(rf'^(  {re.escape(fact)}:\s*\[)([^\]]*)(\])', patient_text, re.MULTILINE)
        if m:
            existing = [d.strip() for d in m.group(2).split(',') if d.strip()]
            if name not in existing:
                existing.append(name)
            patient_text = (patient_text[:m.start()] + m.group(1) + ', '.join(existing)
                             + m.group(3) + patient_text[m.end():])
        else:
            new_lines.append(f"  {fact}: [{name}]")
    if new_lines:
        marker = 'symptom_routing:\n'
        idx = patient_text.index(marker) + len(marker)
        patient_text = patient_text[:idx] + '\n'.join(new_lines) + '\n' + patient_text[idx:]
    yaml.safe_load(patient_text)  # validate before writing
    with open(PATIENT_YAML, 'w') as f:
        f.write(patient_text)

    generate_rules.generate()

    with open(DOCTOR_YAML) as f:
        return yaml.safe_load(f)

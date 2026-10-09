"""
Patient Screening — Flask + Prolog + Ollama

Two production-rule files (doctor_knowledge.yaml, patient_strategy.yaml)
compile into two separate Prolog files. This app never makes a decision
itself: it calls reasoning_engine.pl for every decision, and
llm_conversation.py only for understanding/phrasing natural language.

Run:
    ollama serve  (if not already running as a background service)
    python3 app.py
Then open http://localhost:8090
"""

import os
import re
import subprocess
import tempfile

import yaml
from flask import Flask, request, jsonify, send_from_directory

import generate_rules
import llm_conversation as conv
import doctor_intake

BASE = os.path.dirname(os.path.abspath(__file__))

DOCTOR_KB = PATIENT_STRATEGY = ALL_DISEASES = SYMPTOM_ROUTING = None
CATEGORY_INTRO = KNOWN_FACTS = DISEASE_CATEGORY = QUESTION_TEXT = None


def reload_knowledge():
    """(Re)loads both production-rule files into the module-level globals
    every route reads from, and regenerates the compiled Prolog rules.
    Called at startup, and again right after a doctor confirms a new
    condition — so it's live immediately, no server restart needed."""
    global DOCTOR_KB, PATIENT_STRATEGY, ALL_DISEASES, SYMPTOM_ROUTING
    global CATEGORY_INTRO, KNOWN_FACTS, DISEASE_CATEGORY, QUESTION_TEXT

    generate_rules.generate()
    with open(os.path.join(BASE, 'doctor_knowledge.yaml')) as f:
        DOCTOR_KB = yaml.safe_load(f)
    with open(os.path.join(BASE, 'patient_strategy.yaml')) as f:
        PATIENT_STRATEGY = yaml.safe_load(f)

    ALL_DISEASES = list(DOCTOR_KB['diseases'].keys())
    SYMPTOM_ROUTING = PATIENT_STRATEGY['symptom_routing']
    CATEGORY_INTRO = PATIENT_STRATEGY.get('category_intro', {})
    # Recognizable vocabulary = every confirming fact (doctor's file) PLUS
    # every routing-only opening symptom (patient's file, e.g. "cough"
    # routes to asthma/tuberculosis but isn't itself a confirming fact).
    KNOWN_FACTS = ({s['fact'] for d in DOCTOR_KB['diseases'].values() for s in d['symptoms']}
                   | set(SYMPTOM_ROUTING.keys()))
    DISEASE_CATEGORY = {name: d['category'] for name, d in DOCTOR_KB['diseases'].items()}
    QUESTION_TEXT = {s['fact']: s['question']
                     for d in DOCTOR_KB['diseases'].values() for s in d['symptoms']}


reload_knowledge()

app = Flask(__name__, static_folder='static')

YES_WORDS = {'yes', 'yeah', 'yep', 'yup', 'correct', 'right', 'sure', 'definitely'}
NO_WORDS = {'no', 'nope', 'not really', 'never'}


def deterministic_answer(text):
    tl = re.sub(r'[^a-z\s]', ' ', text.lower())
    words = set(tl.split())
    if words & YES_SET:
        return 'yes'
    if words & NO_SET:
        return 'no'
    return 'unrecognized'


YES_SET = {w for phrase in YES_WORDS for w in phrase.split()}
NO_SET = {w for phrase in NO_WORDS for w in phrase.split()} - YES_SET


def narrow_candidates(symptom, current):
    """Strategy rule: intersect with the symptom's routing list, preserving
    whichever order was established first. Never narrows to empty."""
    route = SYMPTOM_ROUTING.get(symptom)
    if route is None:
        return current
    if current is None:
        return list(route)
    narrowed = [d for d in current if d in route]
    return narrowed if narrowed else current


def run_engine(facts, asked, candidates):
    """facts: {fact_name: intensity}. candidates: list or None."""
    fact_lines = ''.join(f':- assertz(fact({f}, {i})).\n' for f, i in facts.items())
    asked_lines = ''.join(f':- assertz(asked({a})).\n' for a in asked)
    cand_term = 'none' if candidates is None else '[' + ', '.join(candidates) + ']'

    doctor_pl = os.path.join(BASE, 'rules', 'doctor_rules.pl')
    patient_pl = os.path.join(BASE, 'rules', 'patient_rules.pl')
    engine_pl = os.path.join(BASE, 'reasoning_engine.pl')

    script = (
        f":- consult('{doctor_pl}').\n"
        f":- consult('{patient_pl}').\n"
        f":- consult('{engine_pl}').\n"
        + fact_lines + asked_lines
        + f":- run({cand_term}).\n:- halt.\n"
    )
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pl', delete=False) as tf:
        tf.write(script)
        path = tf.name
    try:
        result = subprocess.run(['swipl', '-q', '-s', path], capture_output=True, text=True, timeout=15)
        line = result.stdout.splitlines()[0].strip() if result.stdout.strip() else ''
    except subprocess.TimeoutExpired:
        return {'type': 'error', 'detail': 'engine timed out'}
    finally:
        os.unlink(path)

    if not line:
        return {'type': 'error', 'detail': (result.stderr or '')[:400]}
    parts = line.split('\t')
    tag = parts[0]
    if tag == 'NEED_ANSWER' and len(parts) >= 4:
        return {'type': 'need_answer', 'question': parts[1], 'fact': parts[2], 'disease': parts[3]}
    if tag == 'DIAGNOSED' and len(parts) >= 5:
        return {'type': 'diagnosed', 'disease': parts[1],
                'matched': [m for m in parts[2].split(',') if m],
                'confidence': int(parts[3]), 'reason': parts[4]}
    if tag == 'NO_DIAGNOSIS':
        return {'type': 'no_diagnosis'}
    if tag == 'NO_RECOGNIZED_SYMPTOM':
        return {'type': 'no_recognized_symptom'}
    return {'type': 'error', 'detail': line}


WELCOME = (
    "Hi, I'm glad you came in today. What's been bothering you lately? "
    "Tell me in your own words — I'll ask some follow-up questions as we go."
)


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/start', methods=['POST'])
def start():
    session = {
        'facts': {}, 'asked': [], 'candidates': None,
        'pending_fact': None, 'pending_question': None, 'pending_disease': None,
        'last_category': None, 'done': False, 'questions_asked': 0, 'severity_queue': [],
    }
    return jsonify({'message': WELCOME, 'session': session})


def apply_new_facts(session, new_facts, source_text=''):
    """new_facts: list of {fact, intensity, stated}. Updates session facts
    and queues candidate narrowing (see narrow_batch) for each newly
    recognized fact. Returns the list of facts whose severity needs an
    explicit follow-up question.

    The model's own "stated" flag is NOT trusted on its own — small local
    models don't reliably say "I don't know" when told to; they've been
    observed inventing a plausible-looking number instead of returning
    null. So this cross-checks independently: a fact only counts as
    "stated" if the RAW message itself contains something
    conv.parse_severity can actually find (a digit or a recognized
    severity word). If the model claims a severity the raw text doesn't
    support, that's overridden back to unstated — better to ask an extra
    question than to silently fabricate a rating."""
    text_has_severity_cue = conv.parse_severity(source_text) is not None
    unstated = []
    new_fact_names = []
    for item in new_facts:
        f, i = item['fact'], item['intensity']
        if f not in session['facts']:
            session['facts'][f] = i
            if f not in session['asked']:
                session['asked'].append(f)
            new_fact_names.append(f)
            stated = item.get('stated', True) and text_has_severity_cue
            if not stated:
                unstated.append(f)
    narrow_batch(session, new_fact_names)
    return unstated


def narrow_batch(session, fact_names):
    """Applies the strategy rule to a batch of newly recognized facts.

    If candidates haven't been established yet (this is the first
    symptom information of the conversation), the routes of ALL facts in
    the batch are UNIONED, not intersected — several symptoms reported
    together in one opening statement are independent leads a doctor
    would want to explore in parallel ("fever and dizziness" opens up
    both an infectious angle and a blood-count angle), not facts expected
    to already agree on one disease. Intersecting them here would let
    whichever fact happened to be processed first silently win and
    discard every candidate the other fact pointed to.

    Once candidates ARE established, each subsequent new fact still
    narrows (intersects) as before — that progressive narrowing is
    exactly the behavior that's supposed to happen turn by turn."""
    routed = [SYMPTOM_ROUTING[f] for f in fact_names if f in SYMPTOM_ROUTING]
    if session['candidates'] is None:
        if routed:
            union = []
            for route in routed:
                for d in route:
                    if d not in union:
                        union.append(d)
            session['candidates'] = union
        return
    for f in fact_names:
        session['candidates'] = narrow_candidates(f, session['candidates'])


def severity_question(fact):
    return f"On a scale of 1 (mild) to 5 (severe), how would you rate the {fact.replace('_', ' ')}?"


def category_lead_in(session, disease):
    # Never name a body system on the very first question of the whole
    # conversation — doing that off one unconfirmed opening symptom
    # presents a guess as a finding, which isn't how a real consultation
    # opens (a real doctor asks a few neutral follow-ups first). From the
    # second question onward, naming a *change* in direction is fine.
    first_question = session.get('questions_asked', 0) == 0
    if first_question:
        return ''
    cat = DISEASE_CATEGORY.get(disease)
    if cat and cat != session.get('last_category'):
        session['last_category'] = cat
        phrase = CATEGORY_INTRO.get(cat, cat)
        return f"Let's look into {phrase}."
    return ''


@app.route('/chat', methods=['POST'])
def chat():
    body = request.json
    user_message = body['message']
    session = body['session']
    session.setdefault('questions_asked', 0)
    session.setdefault('severity_queue', [])

    # A finished conversation shouldn't keep processing new messages —
    # the UI already disables input once done, but the server should
    # never rely on the client alone for that; without this, a stray
    # message sent after a result was reached could still be run through
    # open-vocabulary extraction and silently add facts to a session
    # that's already concluded.
    if session.get('done'):
        return jsonify({
            'message': "This screening has already finished — please restart to begin a new one.",
            'session': session,
        })

    # --- If we're waiting on an explicit severity rating, that takes
    # priority over everything else this turn. This replaces silently
    # assuming "moderate" whenever a patient confirms a symptom without
    # elaborating — now it's a real, visible question of its own, the
    # same way a doctor would actually ask "how bad, 1 to 5?" rather than
    # guessing. ---
    if session['severity_queue']:
        fact = session['severity_queue'][0]
        sev = conv.parse_severity(user_message)
        if sev is None:
            sev_q = severity_question(fact)
            explanation = conv.explain_fact(user_message, fact.replace('_', ' '), sev_q)
            if explanation:
                reply = f"{explanation}\n\n{sev_q}"
            else:
                reply = f"Sorry, just a number from 1 (mild) to 5 (severe) works — {sev_q}"
            return jsonify({'message': reply, 'session': session})
        session['facts'][fact] = sev
        session['severity_queue'].pop(0)
        if session['severity_queue']:
            return jsonify({
                'message': f"Got it. And {severity_question(session['severity_queue'][0])}",
                'session': session,
            })
        # Queue drained — fall through to continue the conversation below
        # with an empty user message segment (nothing new to extract).
        return _continue_conversation(session, pending_resolved=True)

    pending_fact = session.get('pending_fact')
    pending_question = session.get('pending_question')

    # Extracted exactly ONCE per turn — this call used to run a second
    # time, unconditionally, further down. On a short ambiguous reply
    # (e.g. a bare "not") that second independent call could hallucinate
    # an unrelated symptom and silently narrow out a perfectly valid
    # candidate the patient hadn't actually been ruled out for yet.
    #
    # Short messages are also a real hallucination risk on their own: a
    # bare "yes" handed to a ~40-code open vocabulary has been observed
    # inventing half a dozen unrelated symptoms the patient never said a
    # word about. BUT that only applies when a question is pending and a
    # short reply is almost certainly just answering it — a short reply
    # to an OPEN question (no pending_fact at all, e.g. the very first
    # thing a patient says) is completely normal ("vomiting", "a cough")
    # and must still be extracted normally, or real opening symptoms get
    # silently dropped. The grounded pending-question check runs
    # regardless either way, since it's constrained to yes/no/unclear
    # rather than a free vocabulary pick and doesn't share this failure
    # mode.
    significant_words = [w for w in re.sub(r'[^a-z\s]', ' ', user_message.lower()).split()
                          if w not in (YES_SET | NO_SET)]
    skip_extraction = pending_fact and len(significant_words) < 3

    # Before candidates exist, ONLY symptoms with a routing entry are
    # offered as valid extraction targets — never the full vocabulary.
    # Deeper, disease-specific confirming facts (e.g. "severe_abdominal_
    # pain", which only exists inside nausea_vomiting's own question
    # list) have no routing entry at all, so if the very first symptom
    # of a conversation gets mapped to one of those instead of a real
    # routable symptom, candidates never get established — the engine
    # permanently returns "nothing recognized" no matter what's said
    # afterward, since nothing can ever set candidates again. This was a
    # real, reproduced dead end, not a theoretical one. Once candidates
    # already exist, the full vocabulary is fine again — a non-routing
    # fact recognized later just safely narrows nothing, which is a
    # no-op, not a dead end.
    vocab = set(SYMPTOM_ROUTING.keys()) if session['candidates'] is None else KNOWN_FACTS
    extracted = [] if skip_extraction else conv.extract_facts(user_message, vocab)
    unstated_so_far = []  # facts confirmed this turn with no real severity given

    if pending_fact:
        # Three ways a message can resolve the pending question, checked
        # in order of how much context they use:
        #  1. A cheap deterministic word check — fast, free, catches the
        #     common case ("yes", "no").
        #  2. A grounded LLM check that's told the actual pending question
        #     — this is what correctly handles a patient referring back
        #     ("I already told you I have a fever") instead of requiring
        #     them to restate it in isolation.
        #  3. The general vocabulary extractor — only for catching a
        #     DIFFERENT, newly volunteered symptom in the same message.
        det = deterministic_answer(user_message)
        hit = next((e for e in extracted if e['fact'] == pending_fact), None)
        pending_intensity = hit['intensity'] if hit else None
        pending_stated = hit.get('stated', True) if hit else False

        if det == 'unrecognized' and not hit:
            grounded = conv.interpret_pending_answer(user_message, pending_question)
            if grounded['answer'] in ('yes', 'no'):
                det = grounded['answer']
                if grounded['intensity'] is not None:
                    pending_intensity = grounded['intensity']
                    pending_stated = True

        if det == 'yes' or hit:
            intensity = pending_intensity if pending_intensity is not None else 3
            session['facts'][pending_fact] = intensity
            if pending_fact not in session['asked']:
                session['asked'].append(pending_fact)
            session['candidates'] = narrow_candidates(pending_fact, session['candidates'])
            session['pending_fact'] = None
            session['pending_question'] = None
            if not pending_stated:
                unstated_so_far.append(pending_fact)
            # Anything ELSE volunteered in the same message still counts.
            unstated_so_far += apply_new_facts(session, [e for e in extracted if e['fact'] != pending_fact], user_message)
        elif det == 'no':
            if pending_fact not in session['asked']:
                session['asked'].append(pending_fact)
            session['pending_fact'] = None
            session['pending_question'] = None
            unstated_so_far += apply_new_facts(session, extracted, user_message)
        else:
            # Not a direct answer. A volunteered new symptom?
            if extracted:
                unstated_so_far += apply_new_facts(session, extracted, user_message)
                session['severity_queue'] += [f for f in unstated_so_far if f not in session['severity_queue']]
                if session['severity_queue']:
                    q = severity_question(session['severity_queue'][0])
                    reply = f"Noted, thank you.\n\n{q}"
                    return jsonify({'message': reply, 'session': session})
                reply = f"Noted, thank you. And to finish the earlier question — {pending_question}"
                return jsonify({'message': reply, 'session': session})
            clarification = conv.clarify(user_message, pending_question)
            if clarification:
                reply = f"{clarification}\n\n{pending_question}"
            else:
                reply = f"Sorry, could you answer with a yes or no? {pending_question}"
            return jsonify({'message': reply, 'session': session})
    else:
        unstated_so_far += apply_new_facts(session, extracted, user_message)

    session['severity_queue'] += [f for f in unstated_so_far if f not in session['severity_queue']]
    if session['severity_queue']:
        return jsonify({
            'message': severity_question(session['severity_queue'][0]),
            'session': session,
        })

    return _continue_conversation(session)


def _continue_conversation(session, pending_resolved=False):
    if not session['facts']:
        return jsonify({
            'message': "Could you describe the main thing that's bothering you? "
                       "For example: thirst, a cough, a headache, or feeling tired.",
            'session': session,
        })

    result = run_engine(session['facts'], session['asked'], session['candidates'])

    if result['type'] == 'need_answer':
        session['pending_fact'] = result['fact']
        lead_in = category_lead_in(session, result['disease'])
        phrased = conv.phrase_question(result['question'], lead_in)
        session['pending_question'] = phrased
        session['questions_asked'] += 1
        lead = "Got it, thank you." if pending_resolved else lead_in
        reply = '\n\n'.join(p for p in [lead, phrased] if p) if pending_resolved \
            else '\n\n'.join(p for p in [lead_in, phrased] if p)
        return jsonify({'message': reply, 'session': session, 'debug': result})

    if result['type'] == 'diagnosed':
        session['done'] = True
        # Stated as a confirmed finding, NOT the original question text —
        # reusing the literal question here ("1. Do you feel pain or
        # burning...?") reads exactly like a new question waiting for an
        # answer, which is confusing right when the conversation has
        # actually just ended and input is disabled.
        reasons = [f"{f.replace('_', ' ')} (rated {session['facts'].get(f, '?')}/5)"
                   for f in result['matched']]
        reason_lines = '\n'.join(f"{i+1}. You reported {r}." for i, r in enumerate(reasons))
        why = ("one finding was clinically decisive on its own" if result['reason'] == 'hallmark'
               else f"the combined evidence reached {result['confidence']}% confidence")
        reply = (
            f"Based on what you've told me, this points to **{result['disease'].upper()}** "
            f"— {why}.\n\n{reason_lines}\n\n"
            f"This is a screening suggestion, not a lab-confirmed diagnosis. "
            f"Please follow up with a clinician."
        )
        return jsonify({'message': reply, 'session': session, 'debug': result})

    if result['type'] == 'no_diagnosis':
        session['done'] = True
        return jsonify({
            'message': "I've checked everything I know how to check for based on what you've "
                       "told me, and none of it was a clear enough match. That doesn't mean "
                       "nothing's wrong — it may be a condition I'm not set up to recognize "
                       "yet, or it may need an in-person exam or tests to pin down. Either "
                       "way, please follow up with a clinician rather than relying on this.",
            'session': session,
        })

    return jsonify({
        'message': "Could you describe the main thing that's bothering you a little more clearly?",
        'session': session,
    })


# ---------------------------------------------------------------------------
# Doctor-side knowledge acquisition — writes ONLY to doctor_knowledge.yaml
# (the doctor production-rule file), never to patient_strategy.yaml's own
# strategy rules. See doctor_intake.py.
# ---------------------------------------------------------------------------

@app.route('/doctor')
def doctor_page():
    return send_from_directory('static', 'doctor.html')


@app.route('/doctor/start', methods=['POST'])
def doctor_start():
    session = doctor_intake.new_session()
    return jsonify({'message': doctor_intake.start_message(), 'session': session})


@app.route('/doctor/chat', methods=['POST'])
def doctor_chat():
    body = request.json
    reply, session, draft = doctor_intake.step(body['session'], body['message'])
    return jsonify({'message': reply, 'session': session, 'draft': draft})


@app.route('/doctor/confirm', methods=['POST'])
def doctor_confirm():
    draft = request.json['draft']
    try:
        doctor_intake.commit_draft(draft)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Could not save: {e}'}), 500

    reload_knowledge()  # live immediately, no restart

    return jsonify({
        'ok': True,
        'message': f"Added to the knowledge base — \"{draft['name']}\" is now part of "
                    f"live screening, effective immediately.",
        'diseases': ALL_DISEASES,
    })


@app.route('/doctor/discard', methods=['POST'])
def doctor_discard():
    return jsonify({'ok': True})


if __name__ == '__main__':
    print('\nPatient Screening running at http://localhost:8090')
    print('Doctor knowledge acquisition at http://localhost:8090/doctor\n')
    app.run(debug=False, port=8090)

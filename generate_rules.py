#!/usr/bin/env python3
"""
Compiles the two production-rule YAML files into two SEPARATE Prolog
files — doctor_rules.pl and patient_rules.pl. They stay separate on
disk on purpose: the doctor's file is medical knowledge (what evidence
points to what disease), the patient's file is conversation strategy
(what to ask next, given what's already known). Neither file needs the
other to be readable on its own.

Run after editing either YAML file, or let app.py call this at startup.
"""

import os
import yaml

BASE = os.path.dirname(os.path.abspath(__file__))


def _esc(text):
    return text.replace("'", "''")


def generate():
    with open(os.path.join(BASE, 'doctor_knowledge.yaml')) as f:
        doctor = yaml.safe_load(f)
    with open(os.path.join(BASE, 'patient_strategy.yaml')) as f:
        patient = yaml.safe_load(f)

    os.makedirs(os.path.join(BASE, 'rules'), exist_ok=True)
    _write_doctor_rules(doctor)
    _write_patient_rules(patient, doctor)
    print('[generate_rules] Wrote rules/doctor_rules.pl and rules/patient_rules.pl')


def _write_doctor_rules(doctor):
    lines = [
        '% ============================================================',
        '% DOCTOR PRODUCTION RULES — AUTO-GENERATED from doctor_knowledge.yaml',
        '% Medical knowledge only. Do not hand-edit — edit the YAML and',
        '% regenerate, or confirm a new condition through the doctor',
        '% conversation, which writes to the YAML for you.',
        '% ============================================================',
        '',
        ':- discontiguous disease_category/2.',
        ':- discontiguous disease_threshold/2.',
        ':- discontiguous disease_symptom/5.',
        '',
    ]
    for name, d in doctor['diseases'].items():
        symptoms = sorted(d['symptoms'], key=lambda s: -s.get('severity', 3))
        lines.append(f"disease_category({name}, {d['category']}).")
        lines.append(f"disease_threshold({name}, {d['threshold']}).")
        for s in symptoms:
            hallmark = 'true' if s.get('hallmark') else 'false'
            q = _esc(s['question'])
            lines.append(
                f"disease_symptom({name}, {s['fact']}, {s.get('severity', 3)}, "
                f"{hallmark}, '{q}')."
            )
        lines.append('')
    with open(os.path.join(BASE, 'rules', 'doctor_rules.pl'), 'w') as f:
        f.write('\n'.join(lines))


def _write_patient_rules(patient, doctor):
    lines = [
        '% ============================================================',
        '% PATIENT PRODUCTION RULES — AUTO-GENERATED from patient_strategy.yaml',
        '% Conversation strategy only — no medical judgment lives here.',
        '% ============================================================',
        '',
    ]
    for symptom, diseases in patient['symptom_routing'].items():
        dl = ', '.join(diseases)
        lines.append(f"symptom_routes_to({symptom}, [{dl}]).")
    lines.append('')
    for cat, phrase in patient.get('category_intro', {}).items():
        lines.append(f"category_phrase({cat}, '{_esc(phrase)}').")
    lines.append('')

    # Every recognizable fact in the system, derived from the doctor's
    # file — the patient-side engine needs this to know what counts as
    # an answerable symptom code at all, without duplicating the list
    # by hand in two places.
    all_facts = sorted({
        s['fact']
        for d in doctor['diseases'].values()
        for s in d['symptoms']
    })
    for fact in all_facts:
        lines.append(f"known_fact({fact}).")

    with open(os.path.join(BASE, 'rules', 'patient_rules.pl'), 'w') as f:
        f.write('\n'.join(lines))


if __name__ == '__main__':
    generate()

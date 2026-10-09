% ============================================================
% PATIENT PRODUCTION RULES — AUTO-GENERATED from patient_strategy.yaml
% Conversation strategy only — no medical judgment lives here.
% ============================================================

symptom_routes_to(elevated_glucose, [diabetes, hypertension]).
symptom_routes_to(polyuria, [diabetes, diabetes_insipidus, kidney_disorder, uti]).
symptom_routes_to(polydipsia, [diabetes, diabetes_insipidus, dehydration, kidney_disorder]).
symptom_routes_to(increased_hunger, [diabetes]).
symptom_routes_to(headache, [hypertension, anemia]).
symptom_routes_to(elevated_bp, [hypertension, diabetes]).
symptom_routes_to(chest_pain, [hypertension, anemia]).
symptom_routes_to(fatigue, [anemia, diabetes, hypertension]).
symptom_routes_to(pale_skin, [anemia]).
symptom_routes_to(dizziness, [anemia, hypertension]).
symptom_routes_to(nausea, [nausea_vomiting, diabetes, anemia]).
symptom_routes_to(vomiting, [nausea_vomiting]).
symptom_routes_to(dysuria, [uti]).
symptom_routes_to(urinary_frequency, [uti, diabetes, diabetes_insipidus, kidney_disorder]).
symptom_routes_to(cough, [asthma, tuberculosis]).
symptom_routes_to(shortness_of_breath, [asthma, tuberculosis, anemia]).
symptom_routes_to(fever, [tuberculosis, uti, nausea_vomiting]).
symptom_routes_to(night_sweats, [tuberculosis]).
symptom_routes_to(weight_loss, [tuberculosis, diabetes]).
symptom_routes_to(other, [diabetes, hypertension, anemia, uti, asthma, tuberculosis]).

category_phrase(metabolic, 'a possible metabolic cause').
category_phrase(endocrine, 'a hormonal cause').
category_phrase(renal, 'whether your kidneys are involved').
category_phrase(cardiovascular, 'your cardiovascular system').
category_phrase(hematologic, 'your blood count').
category_phrase(urinary, 'your urinary system').
category_phrase(respiratory, 'your respiratory system').
category_phrase(gastrointestinal, 'your digestive system').

known_fact(blood_in_vomit).
known_fact(cant_keep_fluids_down).
known_fact(chest_tightness).
known_fact(chronic_cough).
known_fact(coughing_blood).
known_fact(dilute_urine).
known_fact(dizziness).
known_fact(dry_mouth).
known_fact(dysuria).
known_fact(elevated_bp).
known_fact(elevated_glucose).
known_fact(exercise_triggered).
known_fact(fatigue).
known_fact(fever_with_nausea).
known_fact(flank_pain).
known_fact(foamy_urine).
known_fact(high_hba1c).
known_fact(history_of_hypertension).
known_fact(hypertension_headache).
known_fact(increased_hunger).
known_fact(leg_swelling).
known_fact(low_fluid_intake).
known_fact(night_sweats).
known_fact(nocturia).
known_fact(normal_glucose).
known_fact(on_bp_medication).
known_fact(pale_skin).
known_fact(persistent_cough).
known_fact(polydipsia).
known_fact(polyuria).
known_fact(recent_food).
known_fact(reduced_urination).
known_fact(severe_abdominal_pain).
known_fact(suprapubic_pain).
known_fact(tb_exposure).
known_fact(unexplained_weight_loss).
known_fact(urinary_frequency).
known_fact(urinary_urgency).
known_fact(wheezing).
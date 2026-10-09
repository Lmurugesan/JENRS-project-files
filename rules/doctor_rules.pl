% ============================================================
% DOCTOR PRODUCTION RULES — AUTO-GENERATED from doctor_knowledge.yaml
% Medical knowledge only. Do not hand-edit — edit the YAML and
% regenerate, or confirm a new condition through the doctor
% conversation, which writes to the YAML for you.
% ============================================================

:- discontiguous disease_category/2.
:- discontiguous disease_threshold/2.
:- discontiguous disease_symptom/5.

disease_category(diabetes, metabolic).
disease_threshold(diabetes, 60).
disease_symptom(diabetes, elevated_glucose, 5, true, 'Have you been told your blood sugar or glucose is high?').
disease_symptom(diabetes, high_hba1c, 5, true, 'Have you had a blood test showing high HbA1c?').
disease_symptom(diabetes, polyuria, 3, false, 'Are you urinating much more often than usual?').
disease_symptom(diabetes, polydipsia, 3, false, 'Are you feeling extremely thirsty most of the time?').
disease_symptom(diabetes, increased_hunger, 3, false, 'Have you noticed you''re hungrier than usual, even after eating?').
disease_symptom(diabetes, fatigue, 2, false, 'Are you feeling unusually tired or fatigued?').

disease_category(diabetes_insipidus, endocrine).
disease_threshold(diabetes_insipidus, 60).
disease_symptom(diabetes_insipidus, normal_glucose, 5, true, 'Has your blood sugar been tested and come back normal despite the thirst and urination?').
disease_symptom(diabetes_insipidus, dilute_urine, 4, false, 'Is your urine usually very pale or clear, even when you''ve been drinking little water?').
disease_symptom(diabetes_insipidus, nocturia, 3, false, 'Do you wake up multiple times at night specifically to urinate?').

disease_category(dehydration, metabolic).
disease_threshold(dehydration, 60).
disease_symptom(dehydration, low_fluid_intake, 5, true, 'Have you been drinking noticeably less fluid than usual, or losing fluids from heat, exercise, vomiting, or diarrhea?').
disease_symptom(dehydration, reduced_urination, 4, false, 'Have you been urinating less than usual, with darker urine?').
disease_symptom(dehydration, dry_mouth, 3, false, 'Does your mouth or skin feel unusually dry?').

disease_category(kidney_disorder, renal).
disease_threshold(kidney_disorder, 60).
disease_symptom(kidney_disorder, leg_swelling, 4, true, 'Have you noticed swelling in your legs, ankles, or around your eyes?').
disease_symptom(kidney_disorder, foamy_urine, 4, false, 'Has your urine looked foamy or frothy?').
disease_symptom(kidney_disorder, flank_pain, 3, false, 'Do you have pain in your lower back or sides, below the ribs?').

disease_category(hypertension, cardiovascular).
disease_threshold(hypertension, 60).
disease_symptom(hypertension, on_bp_medication, 5, true, 'Are you currently on any blood pressure medication?').
disease_symptom(hypertension, elevated_bp, 5, true, 'Have you had high blood pressure readings recently?').
disease_symptom(hypertension, history_of_hypertension, 4, false, 'Have you ever been told you have high blood pressure?').
disease_symptom(hypertension, hypertension_headache, 2, false, 'Do you get frequent headaches, especially in the morning?').

disease_category(anemia, hematologic).
disease_threshold(anemia, 60).
disease_symptom(anemia, pale_skin, 4, true, 'Has anyone noticed your skin looks pale lately?').
disease_symptom(anemia, fatigue, 3, false, 'Do you feel unusually weak or tired most of the time?').
disease_symptom(anemia, dizziness, 3, false, 'Do you feel dizzy or lightheaded when you stand up?').

disease_category(uti, urinary).
disease_threshold(uti, 60).
disease_symptom(uti, dysuria, 5, true, 'Do you feel pain or burning when you urinate?').
disease_symptom(uti, suprapubic_pain, 4, false, 'Do you feel pressure or pain in your lower abdomen?').
disease_symptom(uti, urinary_frequency, 3, false, 'Do you need to urinate much more often than usual?').
disease_symptom(uti, urinary_urgency, 3, false, 'Do you get sudden, hard-to-control urges to urinate?').

disease_category(asthma, respiratory).
disease_threshold(asthma, 60).
disease_symptom(asthma, wheezing, 5, true, 'Do you wheeze or hear a whistling sound when you breathe?').
disease_symptom(asthma, chest_tightness, 4, false, 'Do you feel tightness or pressure in your chest?').
disease_symptom(asthma, chronic_cough, 3, false, 'Do you have a recurring cough that gets worse at night?').
disease_symptom(asthma, exercise_triggered, 2, false, 'Does cold air or exercise make your breathing worse?').

disease_category(tuberculosis, respiratory).
disease_threshold(tuberculosis, 60).
disease_symptom(tuberculosis, coughing_blood, 5, true, 'Do you cough up blood or blood-stained mucus?').
disease_symptom(tuberculosis, persistent_cough, 4, false, 'Have you had a cough lasting more than three weeks?').
disease_symptom(tuberculosis, night_sweats, 4, false, 'Do you sweat heavily at night even when it is not hot?').
disease_symptom(tuberculosis, unexplained_weight_loss, 4, false, 'Have you lost weight recently without trying?').
disease_symptom(tuberculosis, tb_exposure, 3, false, 'Have you been in close contact with anyone who had TB?').

disease_category(nausea_vomiting, gastrointestinal).
disease_threshold(nausea_vomiting, 60).
disease_symptom(nausea_vomiting, severe_abdominal_pain, 5, true, 'Is the nausea accompanied by severe abdominal pain?').
disease_symptom(nausea_vomiting, blood_in_vomit, 5, true, 'Have you noticed any blood in your vomit?').
disease_symptom(nausea_vomiting, cant_keep_fluids_down, 4, true, 'Are you unable to keep fluids down at all?').
disease_symptom(nausea_vomiting, recent_food, 3, false, 'Did this start shortly after eating something unusual?').
disease_symptom(nausea_vomiting, fever_with_nausea, 3, false, 'Do you also have a fever along with the nausea?').

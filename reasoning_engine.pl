% ============================================================
% REASONING ENGINE — the only place any decision is actually made.
%
% Reads both production-rule files (doctor_rules.pl, patient_rules.pl)
% but belongs to neither. The LLM and the conversation layer in
% app.py never decide a disease, a question order, or a confidence
% score — they only call into this engine and relay what it says.
%
% Output line formats (read by Python):
%   NEED_ANSWER\tQuestion\tFact\tDisease
%   DIAGNOSED\tDisease\tMatchedFacts\tConfidence\tReason
%   NO_DIAGNOSIS
%   NO_RECOGNIZED_SYMPTOM
% ============================================================

:- dynamic fact/2, asked/1.          % fact(Name, Intensity) ; asked(Name)
:- use_module(library(lists)).


% --- Strategy: narrow the candidate list using patient_rules.pl ---
% Folds one newly recognized symptom into the current candidate set.
% Order is preserved from whichever routing list established it first
% (a hand-authored clinical priority) — never re-sorted afterward.

narrow_candidates(Symptom, CurrentIn, CurrentOut) :-
    symptom_routes_to(Symptom, Route), !,
    ( CurrentIn == none ->
        CurrentOut = Route
    ;
        include([D]>>member(D, Route), CurrentIn, Narrowed),
        ( Narrowed == [] -> CurrentOut = CurrentIn ; CurrentOut = Narrowed )
    ).
narrow_candidates(_, CurrentIn, CurrentIn).   % unrouted symptom: no change


% --- Doctor knowledge: confidence score for one candidate disease ---
% confidence(D) = sum(severity*intensity for confirmed facts)
%                 / sum(severity*5 for every question D has)  * 100
% A hallmark fact confirmed at any intensity >= 3 already clears a
% typical 60% threshold on its own — this is not a separate code path,
% it falls out of the same formula every other fact uses.

max_possible(Disease, Max) :-
    findall(Sev, disease_symptom(Disease, _, Sev, _, _), Sevs),
    maplist([S,M]>>(M is S*5), Sevs, Maxes),
    sum_list(Maxes, Max).

confirmed_evidence(Disease, Evidence, MatchedFacts) :-
    findall(F-Ev, (
        disease_symptom(Disease, F, Sev, _, _),
        fact(F, Intensity),
        Ev is Sev * Intensity
    ), Pairs),
    pairs_keys_values(Pairs, MatchedFacts, Evs),
    sum_list(Evs, Evidence).

confidence(Disease, Pct) :-
    confirmed_evidence(Disease, Evidence, _),
    max_possible(Disease, Max),
    ( Max =:= 0 -> Pct = 0 ; Pct is round(Evidence * 100 / Max) ).

hallmark_confirmed(Disease, Fact) :-
    disease_symptom(Disease, Fact, _, true, _),
    fact(Fact, Intensity),
    Intensity >= 3.


% --- Ask one question (or silently skip if already known) ---

ask_one(Question, Fact, Disease) :-
    ( fact(Fact, _) -> true
    ; asked(Fact)   -> true
    ;
        format('NEED_ANSWER\t~w\t~w\t~w~n', [Question, Fact, Disease]),
        halt
    ).


% --- Investigate one candidate disease: ask its unanswered questions,
% highest severity first, stopping the moment either a hallmark fact
% is confirmed or the confidence threshold is reached. ---

investigate_disease(Disease) :-
    findall(Sev-Fact-Q, disease_symptom(Disease, Fact, Sev, _, Q), Triples),
    sort(0, @>=, Triples, Ordered),     % highest severity first
    ask_each(Ordered, Disease).

ask_each([], _).
ask_each([_Sev-Fact-_Q|Rest], Disease) :-
    fact(Fact, _), !,                    % already known, skip silently
    ( hallmark_confirmed(Disease, Fact) -> report_confirmed(Disease, hallmark)
    ; ask_each(Rest, Disease)
    ).
ask_each([_Sev-Fact-Q|Rest], Disease) :-
    ask_one(Q, Fact, Disease),
    ( hallmark_confirmed(Disease, Fact) -> report_confirmed(Disease, hallmark)
    ; confidence(Disease, Pct), disease_threshold(Disease, Thresh), Pct >= Thresh ->
        report_confirmed(Disease, threshold)
    ; ask_each(Rest, Disease)
    ).

report_confirmed(Disease, Reason) :-
    confirmed_evidence(Disease, _, MatchedFacts),
    confidence(Disease, Pct),
    atomic_list_concat(MatchedFacts, ',', MatchedStr),
    format('DIAGNOSED\t~w\t~w\t~w\t~w~n', [Disease, MatchedStr, Pct, Reason]),
    halt.


% --- Entry point: run the candidate list in order ---

run_candidates([]) :-
    write('NO_DIAGNOSIS'), nl, halt.
run_candidates([Disease|Rest]) :-
    investigate_disease(Disease),
    % investigate_disease only returns (without halting) when this
    % candidate is exhausted without confirming — move on silently.
    % (Nothing is printed here: this engine only ever emits ONE line,
    % whichever of NEED_ANSWER / DIAGNOSED / NO_DIAGNOSIS is terminal —
    % the caller reads exactly one line of stdout as the result.)
    run_candidates(Rest).

run(none) :-
    write('NO_RECOGNIZED_SYMPTOM'), nl, halt.
run(Candidates) :-
    is_list(Candidates),
    run_candidates(Candidates).

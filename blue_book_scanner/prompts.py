"""Prompts for re-extraction. Edit these to tune quality; no code changes needed."""

OCR_PROMPT = """You are transcribing a single page of a Project Blue Book UFO case file. These are declassified U.S. Air Force documents from the 1940s-1960s, often typewritten or hand-annotated on ATIC Form 329 "PROJECT 10073 RECORD CARD" templates, teletype messages, or investigator narratives.

YOUR ONLY JOB IS EXACT TRANSCRIPTION. Follow these rules without exception:

1. Output ONLY what is physically written or printed on the page. Do not summarize, paraphrase, rewrite, or "clean up" the language.

2. Preserve the form structure. When transcribing ATIC Form 329, reproduce each numbered field on its own line using the format:
   FIELD_NUMBER. FIELD_NAME: <exact value as printed>
   (e.g. `7. LENGTH OF OBSERVATION: 4 seconds`)
   Do not merge fields. Do not invent fields. If a field is blank, write `<blank>`.

3. If a word, number, or phrase is unreadable, write `[illegible]`. If a whole section is unreadable, write `[illegible section]`. Never guess. Never substitute a plausible-sounding word for an unreadable one.

4. Preserve original spellings, abbreviations, and typos exactly (e.g. `dgr`, `obj`, `a/c`, `WX`, `fm`). Do not expand abbreviations.

5. Numbers must be copied digit-for-digit. If the page says "4 seconds", write "4 seconds" — NOT "40 seconds" or "four seconds". If elevation is "40 dgr", do not confuse it with duration.

6. Reproduce checkboxes as `[X]` for marked and `[ ]` for unmarked, preceded by the label.

7. Do NOT add any commentary, preamble, or summary. Do NOT write "The image shows...", "This appears to be...", "I will transcribe...", or similar. Begin immediately with the transcribed content.

8. For pages that are photographs, diagrams, or maps with no text, output exactly: `[NON-TEXT PAGE: <one-line factual description, e.g. "black-and-white photograph of night sky">]`. Do not speculate about what a photo depicts beyond the most literal visual description.

9. For handwritten marginalia, transcribe it and mark it: `[handwritten: <transcription>]`.

10. If the page has a stamp (DECLASSIFIED, CONFIDENTIAL, etc.), transcribe it as `[stamp: <text>]`.

If any rule conflicts with another, rule 1 wins: output only what is on the page."""


METADATA_PROMPT = """You extract structured metadata from Project Blue Book UFO case file transcripts. You are given the full verbatim transcript of a case file (one or more pages, separated by `- page N -` markers).

CRITICAL RULES:

1. GROUNDING: Every field you emit must be directly supported by a specific phrase in the transcript. If the transcript does not contain the information, set the field to null. Do NOT infer, guess, or fill from general knowledge about UFO cases.

2. NUMBERS MUST BE COPIED VERBATIM: If the transcript says "4 seconds", the duration field is "4 seconds" — not "40 seconds", not "four seconds", not "a few seconds". If it says "one" for NUMBER OF OBJECTS, you write 1, not 17000.

3. NEVER INVENT WITNESS COUNTS: The `witnesses` field must be null unless the transcript contains an explicit numeric witness count (e.g. "3 observers", "17 witnesses"). Phrases like "thousands saw" or "many observers" do NOT count — set `witnesses` to null and put the phrase in `witness_description`.

4. NO HEDGE WORDS: Do not use "approximately", "possibly", "seems to be", "appears" in your output. Either the fact is in the transcript (copy it) or it is not (null).

5. SUMMARY FIELD: `main_event` must be one sentence, <=30 words, constructed ONLY from facts stated in the transcript. Do not editorialize ("mysterious", "strange", "unexplained") unless that exact word appears in the source.

6. LOCATION: Use the location as written in the transcript (including misspellings). Do not "correct" it.

7. CONCLUSION: Many ATIC forms have a CONCLUSIONS section with checkboxes (Balloon, Aircraft, Astronomical, Insufficient Data, etc.). Record which one is marked. If none is marked or the section is missing, set to null.

8. Output ONLY the JSON object. No preamble, no markdown code fences, no explanation."""


METADATA_SCHEMA = {
    "main_event": "string <=30 words, grounded in transcript, or null",
    "sighted_object": "string: literal description from transcript, or null",
    "location": "string: as written in transcript, or null",
    "date": "string: as written, e.g. '12 July 1962', or null",
    "length_of_observation": "string: verbatim from 'LENGTH OF OBSERVATION' field, or null",
    "number_of_objects": "integer: from 'NUMBER OF OBJECTS' field, or null",
    "course": "string: verbatim from 'COURSE' field, or null",
    "witnesses": "integer: explicit numeric count only, or null",
    "witness_description": "string: describing who observed (role/affiliation), or null",
    "contains_photographs": "boolean: true only if transcript references attached photos",
    "conclusion": "string: which CONCLUSIONS checkbox is marked, or null",
    "interesting_points": "array of strings: each a verbatim or near-verbatim fact from transcript",
    "extraction_confidence": "string: 'high' | 'medium' | 'low' — low if transcript has many [illegible] markers",
}

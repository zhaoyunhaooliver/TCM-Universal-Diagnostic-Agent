================================================================================

TCM-Universal-Diagnostic-Agent
A Universal Framework for TCM Eight-Principles Diagnosis Based on 
Expert Clinical Experience and Knowledge Graph Verification

[1] PROJECT TIMELINE AND DEVELOPMENT LOG
--------------------------------------------------------------------------------
- 2026/07/24: Project initialized with the core objective of establishing a 
  universal framework for TCM eight-principles diagnostic reasoning.
- 2026/08/01: Initial validation focusing on prompt engineering without 
  heavy fine-tuning, leveraging LLM baseline medical comprehension.
- 2026/08/04: Formalized standardized representation guidelines for clinical 
  records and diagnostic inquiry structures.
- 2026/10/05: Deployed the web exploration interface connected to the backend 
  graph database: http://47.116.26.250:8501/
- 2026/11/02: Integrated a canonical corpus containing 702 classical TCM texts.
- 2026/11/08: Completed full-text classical formula extraction and clinical 
  clause aggregation across the Song editions of "Shanghan Zabing Lun" 
  ("Shanghan Lun" and "Jingui Yaolue").


[2] SYSTEM STATUS AND KNOWN LIMITATIONS
--------------------------------------------------------------------------------
- Web Interface: http://47.116.26.250:8501/
- Active Features:
  1. Full-text search and clinical profile display for 309 classical formulas.
  2. Complete preservation of original formula postscripts (usage_info), 
     including decoction methods, dosages, modifications, and contraindications.
  3. Two-book canonical clause aggregation across Shanghan Lun and Jingui Yaolue.
  4. Real-time topology graph rendering powered by Neo4j and Vis.js.

- KNOWN LIMITATION (TO BE RESOLVED):
  Direct search for individual herb entities (single herbs) is currently not 
  supported on the web interface. Users cannot query herbs directly from the 
  search bar at this stage. This is a recognized temporary limitation in the UI 
  query router and will be fully supported in upcoming updates.


[3] KNOWLEDGE GRAPH (KG) UNIFIED NAMESPACE (CURIE SPECIFICATION)
--------------------------------------------------------------------------------
All entities and graph relationships adhere to the following standard prefixes:
- DIS_  : Disease (National Standard GB/T & NHC Classification)
- SYN_  : Syndrome / Pattern (GB/T Classification)
- PRN_  : Therapeutic Principle / Treatment Method (GB/T Classification)
- FOR_  : Formula / Classical Prescription
- HRB_  : Herb / Chinese Materia Medica
- SYM_  : Clinical Symptom
- CASE_ : Real-World Clinical Case
- CLS_  : Canonical Medical Scripture Clause


[4] KNOWLEDGE GRAPH DATASET MANIFEST (17 CSV FILES)
--------------------------------------------------------------------------------

--- ENTITY FILES (8 FILES) ---

1. entities_diseases.csv
   Standard TCM disease entities, including official national revision codes 
   (A01 prefix), historical codes, English names, parent category flags, 
   aliases, and definitions.

2. entities_syndromes.csv
   Standard TCM syndrome/pattern entities, including official national revision 
   codes (B01 prefix), historical codes, English names, category flags, 
   aliases, and definitions.

3. entities_principles.csv
   Standard TCM treatment principle entities, including official national 
   revision codes (C01 prefix), historical codes, English names, category flags, 
   aliases, and operational definitions.

4. entities_formulas.csv
   Classical prescription entities (309 formulas). Retains complete Song 
   dynasty source books, aggregated clause numbers, original compositions, 
   intact postscripts (usage_info), and all clinical indications (clause_text).

5. entities_herbs.csv
   Authentic materia medica entities (477 herbs). Records standard names, 
   authoritative aliases, four natures, five flavors, meridian tropisms, 
   toxicities, origins, and primary indications.

6. entities_symptoms.csv
   Clinical symptom entities. Includes standardized symptom descriptions, 
   anatomical categories, and diagnostic gateway indicators.

7. entities_clinical_cases.csv
   Real-world clinical consultation cases (1,737 records). Records patient 
   demographics, chief complaints, and four-diagnostic findings (pulse and tongue).

8. entities_shanghan_clauses.csv
   Classical clause text repository from Song-dynasty editions of Shanghan 
   Zabing Lun, preserving authentic chapter numbers and scriptural context.


--- TRIPLE AND RELATIONSHIP FILES (9 FILES) ---

1. triples_diseases_hierarchy.csv
   Taxonomic hierarchy for diseases (Child Disease -[IS_SUBCLASS_OF]-> Parent Disease).

2. triples_syndromes_hierarchy.csv
   Taxonomic hierarchy for syndromes (Child Syndrome -[IS_SUBCLASS_OF]-> Parent Syndrome).

3. triples_principles_hierarchy.csv
   Taxonomic hierarchy for treatment principles (Child Principle -[IS_SUBCLASS_OF]-> Parent Principle).

4. triples_formula_contains_herb.csv
   Prescription-herb compatibility network (1,262 edges). Maps Formula to 
   Herb with compatibility role and authentic historical dosages.

5. triples_syndrome_recommended_formulas.csv
   Diagnostic pattern-to-prescription links (Syndrome -[RECOMMENDED_FORMULA]-> Formula).

6. triples_syndrome_symptoms.csv
   Symptom manifestation links (Syndrome -[HAS_SYMPTOM]-> Symptom), distinguishing 
   between core and secondary manifestations.

7. triples_clause_prescribes_formula.csv
   Classical scripture groundings (Clause -[PRESCRIBES_FORMULA]-> Formula).

8. triples_case_prescribed_formulas.csv
   Clinical practice prescribing links (Case -[PRESCRIBED_FORMULA]-> Formula).

9. triples_case_used_herbs.csv
   Clinical practice herb utilization links (Case -[USED_HERB]-> Herb), including 
   actual prescribed dosages and administration notes.


[5] NEXT STEPS
--------------------------------------------------------------------------------
1. Upgrade the web interface to enable single-herb direct search and navigation.
2. Implement fuzzy matching and alias indexing on the frontend query engine.
3. Integrate graph-grounded diagnostic reasoning for eight-principles assessment.
   
================================================================================

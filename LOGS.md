

exercice_data, sent to frontend
{
   "question":"Créer une fonction nommée `validate_password`:  \n- qui prend en paramètre `password` (chaîne de caractères) représentant le mot de passe à tester  \n- qui vérifie si un mot de passe est valide en respectant les critères suivants :  \n    - longueur minimale de 10 caractères.  \n    - ne contient pas les caractères `!`, `?`, `#`, `&` ou `%`  \n    - aucun caractère ne doit se répéter 2 fois à la suite, (par exemple `aab` ne va pas).  \n- si le mot de passe est valide, votre fonction retoure `True`, sinon `False`\n\n"
}


answer_data, kept in backend
{
  "hints": [],
  "correct_answers": [
    {
      "answer": "def validate_password(password):\n    # check longueur minimale\n    if len(password) < 10:\n        return False\n    \n    # check caractères interdits\n    for char in password:\n        if char in \"!?#&%\":\n            return False\n    \n    # check répétitions\n    for i in range(len(password) - 1):\n        if password[i] == password[i + 1]:\n            return False\n    \n    # si tout est ok, alors pw valide\n    return True",
      "explanation": "This is the canonical solution."
    }
  ],
  "expected_result": "",
  "additional_context": "",
  "unit_tests": {
    "setup_code": "",
    "timeout_seconds": 10,
    "test_cases": [
      {
        "description": "ok",
        "test_code": "print(validate_password(\"abcdefghij\"))",
        "expected_output": "True"
      }
   ]
  }
}


# LLM time taken


2.5 pro
steacher ֎ ag took steacher.log 
29213:[2025-08-15 10:28:01,286] INFO exercises.logic: Unit testing for exercise 43 took 0.34 seconds.
29529:[2025-08-15 10:28:29,099] INFO exercises.logic: LLM call for exercise 43 took 27.80 seconds.
29531:[2025-08-15 10:28:29,106] INFO exercises.logic: Total fetch_ai_guidance for exercise 43 took 28.16 seconds.
29533:[2025-08-15 10:28:29,500] INFO exercises.logic: Unit testing for exercise 43 took 0.38 seconds.
29758:[2025-08-15 10:28:32,370] INFO exercises.logic: LLM call for exercise 43 took 2.87 seconds.
29760:[2025-08-15 10:28:32,374] INFO exercises.logic: Total fetch_ai_guidance for exercise 43 took 3.26 seconds.
29762:[2025-08-15 10:28:32,383] INFO exercises.logic: Unit testing for exercise 43 took 0.00 seconds.
29910:[2025-08-15 10:28:49,570] INFO exercises.logic: LLM call for exercise 43 took 17.18 seconds.
29912:[2025-08-15 10:28:49,575] INFO exercises.logic: Total fetch_ai_guidance for exercise 43 took 17.19 seconds.
29914:[2025-08-15 10:28:49,584] INFO exercises.logic: Unit testing for exercise 43 took 0.00 seconds.

2.5 flash, almost 2x faster. but still slow
steacher ֎ ag took steacher.log 
2:[2025-08-15 10:30:36,397] INFO exercises.logic: Unit testing for exercise 43 took 0.32 seconds.
318:[2025-08-15 10:30:50,923] INFO exercises.logic: LLM call for exercise 43 took 14.52 seconds.
320:[2025-08-15 10:30:50,932] INFO exercises.logic: Total fetch_ai_guidance for exercise 43 took 14.86 seconds.
322:[2025-08-15 10:30:51,332] INFO exercises.logic: Unit testing for exercise 43 took 0.39 seconds.
547:[2025-08-15 10:30:52,735] INFO exercises.logic: LLM call for exercise 43 took 1.40 seconds.
549:[2025-08-15 10:30:52,738] INFO exercises.logic: Total fetch_ai_guidance for exercise 43 took 1.79 seconds.
551:[2025-08-15 10:30:52,744] INFO exercises.logic: Unit testing for exercise 43 took 0.00 seconds.
699:[2025-08-15 10:30:56,140] INFO exercises.logic: LLM call for exercise 43 took 3.39 seconds.
701:[2025-08-15 10:30:56,147] INFO exercises.logic: Total fetch_ai_guidance for exercise 43 took 3.40 seconds.
703:[2025-08-15 10:30:56,161] INFO exercises.logic: Unit testing for exercise 43 took 0.00 seconds.
850:[2025-08-15 10:30:58,575] INFO exercises.logic: LLM call for exercise 43 took 2.40 seconds.
852:[2025-08-15 10:30:58,577] INFO exercises.logic: Total fetch_ai_guidance for exercise 43 took 2.42 seconds.
854:[2025-08-15 10:30:58,956] INFO exercises.logic: Unit testing for exercise 43 took 0.37 seconds.
1082:[2025-08-15 10:31:04,639] INFO exercises.logic: LLM call for exercise 43 took 5.68 seconds.
1084:[2025-08-15 10:31:04,643] INFO exercises.logic: Total fetch_ai_guidance for exercise 43 took 6.06 seconds.
1086:[2025-08-15 10:31:04,652] INFO exercises.logic: Unit testing for exercise 43 took 0.00 seconds.
1239:[2025-08-15 10:31:10,272] INFO exercises.logic: LLM call for exercise 43 took 5.61 seconds.
1241:[2025-08-15 10:31:10,276] INFO exercises.logic: Total fetch_ai_guidance for exercise 43 took 5.62 seconds.
1243:[2025-08-15 10:31:10,691] INFO exercises.logic: Unit testing for exercise 43 took 0.41 seconds.
1460:[2025-08-15 10:31:22,456] INFO exercises.logic: LLM call for exercise 43 took 11.76 seconds.
1462:[2025-08-15 10:31:22,459] INFO exercises.logic: Total fetch_ai_guidance for exercise 43 took 12.17 seconds.
1464:[2025-08-15 10:31:22,842] INFO exercises.logic: Unit testing for exercise 43 took 0.38 seconds.

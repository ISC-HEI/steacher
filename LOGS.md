

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




insert into "public"."exercises_exercise" ("answer_data", "course_id", "created_at", "description", "exercise_data", "exercise_type", "id", "order", "title", "updated_at") values (E'{"hints":[],"unit_tests":{"setup_code":"","test_cases":[],"timeout_seconds":5},"correct_answers":[{"answer":"The solution corresponds to the above step-by-step instructions.","explanation":"This is the complete solution, consisting of 3 parts (creation, insertion, query). \\nThe student should insert his-her name and age in the insertion step.\\nThe student may insert more than 1 entry.\\nDon''t bother with setting the VARCHAR''s length for this introductory exercice. "}],"additional_context":"This is the student''s first ever SQL exercise. So we give them the options to solve it step by step if they are brand new to SQL. If they have some experience, we give them the option to solve it in one go. Or even better, we give them the option to skip ahead to the next exercise.\\n\\n\\n### Options\\n\\nFor this specific exercise, the user will be presented with these three options together, in this order:\\n\\n1. Step-by-step mode:\\n   <button id=\\"step_by_step\\" title=\\"Étape par étape\\" comment=\\"Résoudre l''exercice étape par étape; Avec les instructions complètes de ce que vous devez écrire; Conseillé si c''est la première fois que vous utilisez SQL\\"/>\\n\\n2. One big chunk:\\n   <button id=\\"one_shot\\" title=\\"En un seul bloc\\" comment=\\"Résoudre l''exercice en un seul bloc; À vous d''écrire le code SQL; Conseillé si vous avez déjà un peu d''expérience de SQL\\"/>\\n\\n3. Next exercise:\\n   <button id=\\"next_exercise\\" title=\\"Exercice suivant\\" comment=\\"Passer à l''exercice suivant; Conseillé si vous avez déjà une bonne expérience de SQL\\" to=\\"50\\"/>\\n\\nWhen the user selects a button, you will get back the corresponding action id:\\n\\n- `step_by_step`: guide through 3 ordered steps: (1) table creation, (2) data insertion, (3) query. See steps below for more details.\\n- `one_shot`: provide the entire exercise (all 3 steps) as one instruction chunk.\\n- `next_exercise`: do not handle; this is managed by the backend.\\n\\n\\n### Steps\\n\\nWhen the user selects the \\"Step by Step\\" mode, provide the following steps, in this order, one by one, in french. By steps, I mean that you should provide the instructions for each step, wait for the user to complete the step before providing the next one in your next message. Assume the user is brand new to SQL. So don''t be too fussy about the SQL syntax. Still it should be correct. Since you show them the SQL commands, they should be able to copy paste them.\\n\\n      1. Create the database table with the following schema. Type this exact text in the SQL editor on the left:\\n         ```sql\\n         CREATE TABLE students (\\n            id          INTEGER PRIMARY KEY,\\n            name        VARCHAR, \\n            city        VARCHAR,\\n            age         INTEGER\\n         );\\n         ```\\n\\n      2. Now insert some data into the table you just created. Make sure you replace the values with your own:\\n         ```sql\\n         INSERT INTO students (id, name, age) VALUES\\n         (1, ''Raoul Chatigré'', 20);\\n         ```\\n\\n      3. Write a query to retrieve all data from the `students` table.\\n         ```sql\\n         SELECT * FROM students;\\n         ```\\n\\n      4. Now write a query to retrieve the name of the student with id 1.\\n         ```sql\\n         SELECT name FROM students WHERE id = 1;\\n         ```\\n\\nWhen the user selects the \\"One Big Chunk\\" mode, provide the following instruction. \\n\\n      1. Create a database table with the following columns: `id`, `name`, `city`, `age`.\\n      2. Insert some data into the table, using your own values.\\n      3. Write a query to retrieve all data from the `students` table.\\n      4. Write a query to retrieve the name of the student with id 1.\\n\\n      If you need help, don''t hesitate to ask \\n\\nNote that unlike the step-by-step mode, you don''t provide the SQL commands. You just provide the instructions.\\nAssume the user knows some SQL and wants to try by herself. Don''t be too fussy about the SQL syntax. Still it should be correct. You don''t show them the SQL commands, but it''s relatively easy for her to guess what they are.\\n\\nWhen the user selects the \\"Next Exercise\\" mode, do not handle; this is managed by the backend.\\n\\n"}', '11', '2025-08-20 14:25:13.426127+00', 'Vos premiers pas avec SQL: créer une table, insérer une entrée et faire une requête.', E'{"question":"Bienvenue dans SQL! \\n\\nPour ce premier exercice, vous allez créer une table, la remplir avec des données et effectuer une requête.\\n\\nComment voulez-vous résoudre cet exercice?\\n\\n<button id=\\"step_by_step\\" title=\\"Étape par étape\\" comment=\\"Résoudre l''exercice étape par étape; Avec les instructions complètes de ce que vous devez écrire; Conseillé si c''est la première fois que vous utilisez SQL\\"/>\\n\\n<button id=\\"one_shot\\" title=\\"En un seul bloc\\" comment=\\"Résoudre l''exercice en un seul bloc; À vous d''écrire le code SQL; Conseillé si vous avez déjà un peu d''expérience de SQL\\"/>\\n\\n<button id=\\"next_exercise\\" title=\\"Exercice suivant\\" comment=\\"Passer à l''exercice suivant; Conseillé si vous avez déjà une bonne expérience de SQL\\" to=\\"50\\"/>\\n\\n"}', 'sql', '54', 5, 'Welcome to SQL', '2025-08-20 15:56:30.248605+00')
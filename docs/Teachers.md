# Teachers Guide

This guide is intended to help teachers use steacher. It's a work in progress and will be updated regularly.

## General concepts

### Courses, Modules and Exercises

- A course is a collection of modules. E.g. "Introduction to Python", "Algebra 1", etc.
- A module is a collection of exercises. E.g. "Variables", "Loops", etc.
- An exercise is a single exercise that the student will solve.

In a course, teachers can create and manage modules and exercises.

###  Students, Teachers and Cohorts

- steacher has two basic roles: Student and Teacher.
- A teacher is a user who can create and manage courses, modules and exercises.
- A student is a user who can solve exercises and get feedback from the AI.
- A cohort is a group of students. E.g. "Group 1", "Group 2", etc. A cohort belongs to a course.

In a cohort, teachers can monitor the progress of the students and give feedback to the AI.

Teachers can also add existing students to a cohort & invite new students into a cohort.

### Exercice types

There are several exercise types available in steacher:

- Open Question
- Turtle
- Python
- Scala
- SQL

## Writing maths exercises

Math exercises can be written in plain text like any exercise on STeacher, but you can also integrate some LaTeX for cleaner instructions.

It is very simple to integrate:
- inline notations can be added between pairs of "$" as in the exemple below:
```markdown
On considère le cercle $\Gamma$ de centre $(2, 0)$ et de rayon $\sqrt{10}$.
```

- complete LaTeX lines can be added between pairs of "$$" as in the exemple below:
```markdown
$$\text{Pente de d: } \frac{2-1}{5-2} = \frac{1}{3} \Rightarrow \text{pente de e: } -3$$
```

You can use both inline and complete lines LaTeX mixed with plain text in your exercise. 

These are only useful in the "Question" field, as this is the only one that the students will see.
Other fields such as "Description" or the "Answer" and "Explanation" in your correct answers will only be seen by the AI. The AI will recognize these notations and understand them, but it will also understand a raw LaTeX bloc or basic plain text, so don't stress yourself too much about it.


**IMPORTANT WARNING:** With the way the code currently works, the LaTeX will render as explained here **only if "Allow Image Upload" is toggled on**.





## Module Import/Export 

You can now export and import modules between courses.

### Export a Module
1. Go to teacher course details page
2. Find the module you want to export
3. Click the download icon (⬇) in the module header
4. File downloads as `{module_name}_export.json`

### Import a Module
1. Go to teacher course details page of target course
2. Click "Import module" button (top toolbar)
3. Select JSON file in modal
4. Click "Import"
5. If assets missing → error message lists them
6. If successful → page reloads with new module


## Configuration (Prompts)

You can configure the prompts that the AI will use at several levels:
- Global level
- Course level
- Exercise type level
- Exercise level

### Global Level

The global level prompt is the prompt that the AI will use to guide the students through the exercises. Normally, you don't need to configure this.

### Course Level

The course level prompt is the prompt that the AI will use to guide the students through the exercises.

It may contain information about the course contents, objectives, target audience, etc. 

You can also include a large amount of information about the course content itself (e.g. a summary of 5k words), so that in its answers, the AI will refer to parts of the course content itself. Also, you may include which notations to use, which concepts to avoid, etc.

### Exercise-type Level

The exercise-type level prompt is the prompt that the AI will use to guide the students through the exercises of a specific exercise type.

Global, Course  and Exercise-type level prompts can be edited by clicking the "Edit Course" button in the course details page.

### Exercise Level

The exercise level prompt is the prompt that the AI will use to guide the students through a specific exercise.

It should contain specific information about this very exercise, including expected results, hints, expected answer, additional context, unit tests.

#### Exercice question

This is what the student will see when they start the exercise. You can use markdown and LaTeX to format it.

Exercice questions can be translated into the student's language automatically (button `Translate` in the exercise details page). For the moment, only English, French and German are supported.

TODO: support for images in the exercise question.


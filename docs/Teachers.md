# Writing maths exercises
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
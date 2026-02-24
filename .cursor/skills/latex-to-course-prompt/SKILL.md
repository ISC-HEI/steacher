---
name: latex-to-course-prompt
description: Convert a LaTeX course script into a Steacher course_prompt markdown document. Use when a teacher provides a .tex file and wants to create or update a course prompt for Steacher.
---

# LaTeX to Course Prompt Converter

Convert a LaTeX course script into a Steacher `course_prompt` markdown document.

## Workflow

1. **Collect inputs** from the teacher:
   - **LaTeX file** (required): the `.tex` course script
   - **Course objectives** (optional): if not provided, generate them (from the LaTeX file using the conversion principles below) and ask the teacher for confirmation

2. **Convert** the LaTeX body into clean markdown following the conversion principles below.

3. **Assemble** the full course prompt using the template below.

4. **Present** the result for the teacher to review.

## Output Template

The output must follow this structure exactly:

```markdown
## Course objectives

Here are the major objective of this class:

* <objective 1>
* <objective 2>
* ...

## Exercices

Almost all students will work with paper/pencil. Thus, encourage them to upload their work by taking a picture of their sheet. All open_question exercise types should allow for image upload.


## Solutions

**Important:** A student's solution is correct if it is mathematically equivalent to any provided solution, even if written differently. For example:
- $(x - 3)^2 + (y + 4)^2 = 36$ (standard form)
- $(y + 4)^2 + (x - 3)^2 = 36$ (terms reordered)
- $x^2 - 6x + 9 + y^2 + 8y + 16 = 36$ (expanded form)
- $x^2 + y^2 - 6x + 8y - 11 = 0$ (general form)

All of these are correct answers for a circle equation. Always verify mathematical equivalence, not just textual matching.

## Complete math script

Below is the complete script of this class. Use it to ground your answers in the theory that the teacher gave. Refer to its chapters with the correct number so that students can link the present exercise with the theory.

<converted LaTeX content goes here>
```

### Section notes

- **Course objectives**: Generate them (from the LaTeX file using the conversion principles below) and ask the teacher for confirmation if not provided. These are high-level learning goals.
- **Exercices**: This section is boilerplate. Keep it as shown unless the teacher asks for changes.
- **Solutions**: This section is boilerplate. Adapt the examples to match the course's domain (e.g., circle equations for geometry, matrix forms for linear algebra). Keep the principle about mathematical equivalence.
- **Complete math script**: This is where the converted LaTeX goes. It is the bulk of the output.

## Conversion Principles

The goal is to preserve the **mathematical and pedagogical content** of the LaTeX while stripping everything that only exists for PDF rendering. The output is consumed by an LLM as part of a system prompt, so clarity matters more than visual fidelity.

- **Preserve all math** faithfully: `$...$` inline, `$$...$$` block. Expand custom macros — look for `\def`, `\newcommand`, `\renewcommand` at the top of the file (e.g. `\vect{AB}` → `\vec{AB}`, `\real` → `\mathbf{R}`). Keep LaTeX math commands that KaTeX supports.
- **Strip visual-only LaTeX**: colorboxes, textcolors, spacing commands (`\hspace`, `\vspace`, `\quad`), page breaks (`\newpage`, `\pagebreak`), centering, `\displaystyle`, `\renewcommand{\arraystretch}`, `\sloppy`, font sizing. Skip commented-out sections (`%`).
- **Convert formatting**: `{\bf ...}` / `\textbf{...}` → `**...**`. `\textcolor{...}{Théorème:}` → `**Théorème :**` (strip the color, keep the semantic emphasis).
- **Convert structure** to markdown: sections → `###`/`####` headings, `\begin{itemize}` → bullet lists, `\begin{enumerate}` → numbered lists, `tabular`/`array` → markdown tables, images (`\includegraphics`) → `*(Graphique omis)*`.
- **Absolute values in tables**: When converting LaTeX tables to markdown tables, `|` inside math conflicts with the markdown column separator. Use `\lvert`/`\rvert` for absolute values inside table cells (e.g. `$\ln\lvert x\rvert$` instead of `$\ln|x|$`).
- **Keep the original language** (typically French). Do not translate.

Study the sample input/output pair below to see exactly how the conversion should look in practice.

## Output Directory

Write generated course prompt files to `import_tools/imported_exercises/`. Create the directory if it doesn't exist.

## Reference Files

- Sample LaTeX input: `import_tools/samples/sample_script.tex`
- Sample markdown output: `import_tools/samples/sample_course_prompt.md`

Compare these two files to understand the expected transformation in detail.

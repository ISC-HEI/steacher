
# TODO

- [ ] Codemirror: set right syntax suggestions for SQL and Python.
- [ ] add rewards, gamification, etc.

- [ ] Frontend: List exercises in course detail page: make sure non-staff users can't add new exercises or edit existing ones.
- [ ] Frontend: Display completion status for exercises and courses using Trace.complete.
- [ ] Frontend: Mark trace as complete when user finishes an exercise.
- [ ] Frontend: Disable further editing or submissions for completed traces.
- [ ] Frontend: Show user progress (e.g., progress bar, summary).
- [ ] Frontend: Allow users to view their past attempts (traces).
- [ ] Backend: Add endpoints and logic for annotating GuidanceLog and Trace objects for evaluation purposes.
- [ ] Backend: Add admin and UI for annotating/labeling traces and logs.

# LATER
- [] Frontend: style login page at templates/registration/login.html

Fix this interaction

```
For this first exercise, write an SQL query to list all students from the `students` table

select from student
SQL Error: error: relation "student" does not exist

What do you think might be missing after the SELECT keyword in your query on line 1?
```

## Run code in a sandbox

- jobe?
- https://modal.com/docs/examples/safe_code_execution
- piston? https://github.com/engineer-man/piston?tab=readme-ov-file#License
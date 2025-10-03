# {{ course.name }} - Steacher

**Student:** {{ user.username }}  
**Export Date:** {{ export_date|date:"Y-m-d H:i" }}

## Progress Summary

- **Total Exercises Attempted:** {{ total_exercises }}
- **Completed Exercises:** {{ completed_exercises }}
- **Completion Rate:** {{ completion_rate|floatformat:1 }}%

---

{% for module_data in modules_data %}
## {{ module_data.name }}{% if module_data.is_quiz %} 🏆 (Quiz){% endif %}

{% for exercise in module_data.exercises %}
### {{ forloop.counter }}. {{ exercise.title }}

{% if exercise.complete %}**Status:** ✓ Completed{% else %}**Status:** In Progress{% endif %}

{% if exercise.question %}
#### Question

{{ exercise.question }}

{% endif %}
{% if exercise.last_submission %}
#### My Last Submission

{% if exercise.submission_timestamp %}*Submitted on: {{ exercise.submission_timestamp|date:"Y-m-d H:i" }}*{% endif %}

```{% if exercise.exercise_type == "Python" %}python{% elif exercise.exercise_type == "SQL" %}sql{% elif exercise.exercise_type == "Scala" %}scala{% endif %}
{{ exercise.last_submission }}
```

{% endif %}
{% if exercise.correct_answer %}
#### Correct Answer

```{% if exercise.exercise_type == "Python" %}python{% elif exercise.exercise_type == "SQL" %}sql{% elif exercise.exercise_type == "Scala" %}scala{% endif %}
{{ exercise.correct_answer }}
```

{% endif %}
---

{% endfor %}
{% endfor %}

---

*This document was generated automatically by Steacher. You can convert it to PDF using tools like Pandoc, VS Code, or online Markdown-to-PDF converters.*


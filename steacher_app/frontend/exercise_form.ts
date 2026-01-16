import { createApp, defineComponent } from 'vue';
import { csrfFetch, getCsrfToken } from './utils.js';
import { renderMarkdown } from './markdown_utils.js';

interface TestCase {
    description: string;
    test_code: string;
    expected_output: string;
}

interface ExerciseFormData {
    pk: number | null;
    title_i18n: Record<string, string>;
    order: number;
    description_i18n: Record<string, string>;
    question_i18n: Record<string, string>;
    exercise_type: string;
    allow_image_upload: boolean;
    exercise_data: {
        db?: string;
        answer_template?: string;
    };
    answer_data: {
        expected_result?: string;
        additional_context?: string;
        unit_tests: {
            setup_code: string;
            test_cases: TestCase[];
            timeout_seconds: number;
        };
        correct_answers: { answer: string; explanation: string; }[];
        hints: string;
    };
}

document.addEventListener('DOMContentLoaded', function() {
    const appElement = document.getElementById('exercise-form-app');
    const exerciseDataScript = document.getElementById('exercise-form-data');

    if (!appElement || !exerciseDataScript) {
        console.error('Required elements not found!');
        return;
    }

    const rawData: any = JSON.parse(exerciseDataScript.textContent || '{}');
    const initialData: ExerciseFormData = rawData as ExerciseFormData;
    const availableSqlAssets: string[] = Array.isArray(rawData.available_sql_assets) ? rawData.available_sql_assets : [];
    const coursePk: number | null = typeof rawData.course_pk === 'number' ? rawData.course_pk : null;
    const courseName: string = typeof (rawData as any).course_name === 'string' ? (rawData as any).course_name : '';
    const courseDescription: string = typeof (rawData as any).course_description === 'string' ? (rawData as any).course_description : '';

    // Ensure the nested structure for unit tests exists, especially for new exercises.
    if (!initialData.answer_data) {
        initialData.answer_data = { unit_tests: { setup_code: '', test_cases: [], timeout_seconds: 10 }, correct_answers: [], hints: '' };
    }
    if (!initialData.answer_data.unit_tests) {
        initialData.answer_data.unit_tests = { setup_code: '', test_cases: [], timeout_seconds: 10 };
    }
     if (!initialData.answer_data.unit_tests.test_cases) {
        initialData.answer_data.unit_tests.test_cases = [];
    }
    if (!initialData.answer_data.correct_answers) {
        initialData.answer_data.correct_answers = [];
    }
    if (!initialData.answer_data.hints) {
        initialData.answer_data.hints = '';
    }
    if (!initialData.exercise_data) {
        (initialData as any).exercise_data = {};
    }
    if (!(initialData as any).title_i18n) (initialData as any).title_i18n = {};
    if (!(initialData as any).description_i18n) (initialData as any).description_i18n = {};
    if (!(initialData as any).question_i18n) (initialData as any).question_i18n = {};
    if (typeof (initialData as any).allow_image_upload !== 'boolean') {
        (initialData as any).allow_image_upload = false;
    }
    

    const ExerciseFormApp = defineComponent({
        data() {
            return {
                exercise: initialData,
                available_sql_assets: availableSqlAssets,
                loading: false,
                error: null as string | null,
                // Assistant state (ephemeral, desktop only)
                messages: [] as { role: 'user' | 'assistant'; content: string; mode?: string }[],
                draftMessage: '',
                sending: false,
                assistantError: null as string | null,
                lastAppliedSnapshot: null as ExerciseFormData | null,
                lastActionMode: null as 'edit' | 'feedback' | null,
                course_pk: coursePk,
                uiLang: 'en' as 'en' | 'fr' | 'de',
                course_name: courseName,
                course_description: courseDescription,
                previews: {  // for rendering latex & markdown in the preview mode
                    question: false,
                    answers: [] as { answer: boolean; explanation: boolean; }[]
                }
            };
        },
        created() {
            // Initialize previews for existing answers
            if (this.exercise.answer_data && this.exercise.answer_data.correct_answers) {
                this.previews.answers = this.exercise.answer_data.correct_answers.map(() => ({ answer: false, explanation: false }));
            }
        },
        watch: {
            'exercise.exercise_type'(newType, oldType) {
                // Preserve common fields that we want to carry across type changes.
                const oldAnswerTemplate = this.exercise.exercise_data?.answer_template;

                // Reset exercise_data to ensure no fields from the old type are carried over.
                this.exercise.exercise_data = {};

                // Re-initialize fields for the new type.
                if (newType === 'sql') {
                    this.exercise.exercise_data.db = '';
                }

                if (['python', 'sql', 'scala', 'open_question'].includes(newType)) {
                    // Restore answer_template if it was present and is applicable to the new type.
                    this.exercise.exercise_data.answer_template = oldAnswerTemplate || '';
                }
            }
        },
        computed: {
            pageTitle(): string {
                const title = this.exercise.title_i18n?.['en'] || this.exercise.title_i18n?.['fr'] || this.exercise.title_i18n?.['de'] || '';
                return this.exercise.pk ? `Edit Exercise: ${title}` : 'Create New Exercise';
            },
        },
        mounted() {
            // If exercise has draft_notes, display them as first message in assistant panel
            const draftNotes = (this.exercise as any).draft_notes;
            if (draftNotes && typeof draftNotes === 'string' && draftNotes.trim()) {
                this.messages.unshift({
                    role: 'assistant',
                    content: draftNotes,
                    mode: 'draft_notes'
                });
            }
        },
        methods: {
            deepClone<T>(obj: T): T {
                return JSON.parse(JSON.stringify(obj));
            },
            langEmpty(lang: 'en'|'fr'|'de'): boolean {
                const t = (this.exercise.title_i18n?.[lang] || '').trim();
                const d = (this.exercise.description_i18n?.[lang] || '').trim();
                const q = (this.exercise.question_i18n?.[lang] || '').trim();
                return !t || !d || !q;
            },
            getCsrfToken(): string | null { try { return getCsrfToken(); } catch { return null; } },
            buildErrorMessage(result: any, status: number): string {
                let errorMessage = result?.message || `Server error: ${status}`;
                if (result?.details) {
                    errorMessage += '\n\nDetails:\n';
                    result.details.forEach((detail: any) => {
                        errorMessage += `- ${detail.description}\n`;
                        errorMessage += `  - Expected: ${detail.expected_output}\n`;
                        errorMessage += `  - Got: ${detail.actual_output}\n`;
                        if (detail.error) {
                            errorMessage += `  - Error: ${detail.error}\n`;
                        }
                    });
                }
                return errorMessage;
            },
            async performSave(redirectOnSuccess: boolean) {
                this.loading = true;
                this.error = null;

                try {
                    // Save-time warning: missing translations only
                    const missing: string[] = [];
                    (['fr','de'] as const).forEach((lang) => {
                        if (this.langEmpty(lang)) missing.push(lang.toUpperCase());
                    });
                    if (missing.length) {
                        const msg = `Translations\nMissing: ${missing.join(', ')}\n\nProceed to save?`;
                        const proceed = window.confirm(msg);
                        if (!proceed) {
                            this.loading = false;
                            return;
                        }
                    }

                    const csrfToken = this.getCsrfToken();
                    if (!csrfToken) {
                        this.error = 'CSRF token not found!';
                        this.loading = false;
                        return;
                    }
                    const teacherPath = window.location.pathname.replace(/^\/exercises\//, '/teachers/');
                    const response = await csrfFetch(teacherPath, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(this.exercise),
                    });

                    const result = await response.json();
                    if (!response.ok || result.status !== 'success') {
                        throw new Error(this.buildErrorMessage(result, response.status));
                    }

                    const savedPk: number | null = result.exercise_pk ?? null;
                    if (!this.exercise.pk && savedPk) {
                        this.exercise.pk = savedPk;
                        if (this.course_pk != null) {
                            const newPath = `/exercises/courses/${this.course_pk}/edit_exercise/${savedPk}/`;
                            window.history.replaceState(null, '', newPath);
                        }
                    }

                    if (redirectOnSuccess) {
                        const targetId: number | null = savedPk ?? this.exercise.pk ?? null;
                        if (targetId != null) {
                            window.location.href = `/exercises/${targetId}/`;
                        }
                    }
                } catch (err: any) {
                    this.error = err.message || String(err);
                } finally {
                    this.loading = false;
                }
            },
            detectSourceLanguage(): string {
                // Detect which language has content (first non-empty wins)
                const langs = ['en', 'fr', 'de'];
                for (const lang of langs) {
                    if (this.exercise.title_i18n?.[lang]?.trim()) return lang;
                    if (this.exercise.description_i18n?.[lang]?.trim()) return lang;
                    if (this.exercise.question_i18n?.[lang]?.trim()) return lang;
                }
                return 'en'; // fallback
            },
            async translateLanguage(targetLang: 'fr'|'de') {
                this.assistantError = null;
                this.sending = true;
                let csrf: string;
                try { csrf = getCsrfToken(); } catch {
                    this.assistantError = 'CSRF token not found!';
                    this.sending = false;
                    return;
                }
                try {
                    const sourceLang = this.detectSourceLanguage();
                    console.log('[translate_i18n] sending single target', targetLang, 'from source', sourceLang);
                    const response = await csrfFetch('/teachers/ai/translate_i18n/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            course_pk: this.course_pk,
                            source_lang: sourceLang,
                            targets: [targetLang],
                            fields: {
                                title: this.exercise.title_i18n?.[sourceLang] || '',
                                description: this.exercise.description_i18n?.[sourceLang] || '',
                                question: this.exercise.question_i18n?.[sourceLang] || '',
                            },
                            course_context: { name: this.course_name, description: this.course_description },
                        }),
                    });
                    const result = await response.json();
                    console.log('[translate_i18n] response', result);
                    if (!response.ok || result.status !== 'success') {
                        throw new Error(result.message || `Server error: ${response.status}`);
                    }
                    const translations = (result.translations || {})[targetLang] || {};
                    if (translations.title !== undefined) this.exercise.title_i18n[targetLang] = translations.title;
                    if (translations.description !== undefined) this.exercise.description_i18n[targetLang] = translations.description;
                    if (translations.question !== undefined) this.exercise.question_i18n[targetLang] = translations.question;
                } catch (err: any) {
                    this.assistantError = err.message || String(err);
                } finally {
                    this.sending = false;
                }
            },
            async translateAll() {
                console.log('[translate_i18n] translateAll', this.course_pk);
                const sourceLang = this.detectSourceLanguage();
                // Translate to all other languages
                const allLangs: ('en'|'fr'|'de')[] = ['en', 'fr', 'de'];
                const targets = allLangs.filter(lang => lang !== sourceLang) as ('fr'|'de'|'en')[];
                
                this.assistantError = null;
                this.sending = true;
                let csrf2: string;
                try { csrf2 = getCsrfToken(); } catch {
                    this.assistantError = 'CSRF token not found!';
                    this.sending = false;
                    return;
                }
                try {
                    console.log('[translate_i18n] sending batch', targets, 'from source', sourceLang);
                    const response = await csrfFetch('/teachers/ai/translate_i18n/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            course_pk: this.course_pk,
                            source_lang: sourceLang,
                            targets,
                            fields: {
                                title: this.exercise.title_i18n?.[sourceLang] || '',
                                description: this.exercise.description_i18n?.[sourceLang] || '',
                                question: this.exercise.question_i18n?.[sourceLang] || '',
                            },
                            course_context: { name: this.course_name, description: this.course_description },
                        }),
                    });
                    const result = await response.json();
                    console.log('[translate_i18n] batch response', result);
                    if (!response.ok || result.status !== 'success') {
                        throw new Error(result.message || `Server error: ${response.status}`);
                    }
                    const translations = result.translations || {};
                    (targets as string[]).forEach((lang) => {
                        const t = translations[lang] || {};
                        if (t.title !== undefined) this.exercise.title_i18n[lang] = t.title;
                        if (t.description !== undefined) this.exercise.description_i18n[lang] = t.description;
                        if (t.question !== undefined) this.exercise.question_i18n[lang] = t.question;
                    });
                } catch (err: any) {
                    this.assistantError = err.message || String(err);
                } finally {
                    this.sending = false;
                }
            },
            addTestCase() {
                this.exercise.answer_data.unit_tests.test_cases.push({
                    description: '',
                    test_code: '',
                    expected_output: ''
                });
            },
            removeTestCase(index: number) {
                this.exercise.answer_data.unit_tests.test_cases.splice(index, 1);
            },
            addCorrectAnswer() {
                this.exercise.answer_data.correct_answers.push({ answer: '', explanation: '' });
                this.previews.answers.push({ answer: false, explanation: false });
            },
            removeCorrectAnswer(index: number) {
                this.exercise.answer_data.correct_answers.splice(index, 1);
                this.previews.answers.splice(index, 1);
            },
            renderMarkdown(content: string): string {
                try {
                    return renderMarkdown(content, true);
                } catch (err) {
                    console.error('Markdown rendering failed:', err);
                    return content;
                }
            },
            async sendAssistantMessage(mode: 'edit' | 'feedback') {
                if (this.sending) return;

                const message = this.draftMessage.trim();
                
                // For edit mode with empty message, use default improvement prompt
                // For feedback mode, empty message is allowed (general feedback)
                const content = (mode === 'edit' && message === '') 
                    ? '[Clicked on Improve Exercise button]' 
                    : message;

                this.assistantError = null;
                this.sending = true;

                const userMsg = { role: 'user' as const, content: content, mode: mode };
                this.messages.push(userMsg);
                this.draftMessage = '';

                let csrf3: string;
                try { csrf3 = getCsrfToken(); } catch {
                    this.assistantError = 'CSRF token not found!';
                    this.sending = false;
                    return;
                }

                try {
                    const response = await csrfFetch('/teachers/ai/authoring_assistant/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            exercise: this.exercise,
                            messages: this.messages,
                            context: { course_pk: this.course_pk, mode: mode },
                        }),
                    });

                    const result = await response.json();
                    if (!response.ok || result.status !== 'success') {
                        throw new Error(result.message || `Server error: ${response.status}`);
                    }

                    const assistant_message: string = result.assistant_message || '';
                    const updated_exercise: ExerciseFormData = result.updated_exercise || this.exercise;

                    if (mode === 'edit') {
                        // Edit mode: Apply changes and create snapshot for undo
                        // Ensure the nested structure for unit tests exists in the AI's response.
                        if (!updated_exercise.answer_data) {
                            updated_exercise.answer_data = { unit_tests: { setup_code: '', test_cases: [], timeout_seconds: 10 }, correct_answers: [], hints: '' };
                        }
                        if (!updated_exercise.answer_data.unit_tests) {
                            updated_exercise.answer_data.unit_tests = { setup_code: '', test_cases: [], timeout_seconds: 10 };
                        }

                        this.lastAppliedSnapshot = this.deepClone(this.exercise);
                        this.exercise = this.deepClone(updated_exercise);
                        this.lastActionMode = 'edit';
                    } else {
                        // Feedback mode: Display message only, don't modify form
                        this.lastActionMode = 'feedback';
                    }

                    if (assistant_message) {
                        this.messages.push({ role: 'assistant', content: assistant_message, mode: mode });
                    }
                } catch (err: any) {
                    this.assistantError = err.message || String(err);
                } finally {
                    this.sending = false;
                }
            },
            undoLastAIEdit() {
                if (!this.lastAppliedSnapshot || this.lastActionMode !== 'edit') return;
                this.exercise = this.deepClone(this.lastAppliedSnapshot);
                this.lastAppliedSnapshot = null;
                this.lastActionMode = null;
            },
            async saveExercise() { return this.performSave(true); },
            async saveAndContinue() { return this.performSave(false); }
        }
    });

    const app = createApp(ExerciseFormApp);
    app.config.compilerOptions.delimiters = ['[[', ']]'];
    app.mount('#exercise-form-app');
});

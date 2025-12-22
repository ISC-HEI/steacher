import { createApp, defineComponent, ref, onMounted, onUnmounted, computed } from 'vue';
import { csrfFetch } from './utils.js';

interface Exercise {
    id: number;
    title: string;
    exercise_type: string;
    is_draft: boolean;
    draft_notes: string;
    order: number;
    has_solution: boolean;
}

const ReviewApp = defineComponent({
    setup() {
        const exercises = ref<Exercise[]>([]);
        const loading = ref(true);
        const sessionStatus = ref<string>('active'); // active, building, completed, error
        const coursePk = ref<number>(0);
        const messageToTeacher = ref<string | null>(null);
        const errorsToTeacher = ref<string | null>(null);
        const errorMessage = ref<string | null>(null);
        const error = ref<string | null>(null);
        const refreshInterval = ref<number | null>(null);
        const sessionId = parseInt((document.getElementById('session-id') as HTMLInputElement)?.value || '0');

        const allExercisesReady = computed(() => {
            if (exercises.value.length === 0) return false;
            return exercises.value.every(ex => !ex.is_draft);
        });

        const hasError = computed(() => {
            return sessionStatus.value === 'error';
        });

        const isProcessing = computed(() => {
            return sessionStatus.value === 'building';
        });

        const fetchExercises = async () => {
            try {
                const response = await fetch(`/teacher/authoring-assistant/session/${sessionId}/review/`, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                
                if (!response.ok) throw new Error('Failed to fetch exercises');
                
                const data = await response.json();
                exercises.value = data.exercises;
                sessionStatus.value = data.status;
                coursePk.value = data.course_pk;
                messageToTeacher.value = data.message_to_teacher || null;
                errorsToTeacher.value = data.errors_to_teacher || null;
                errorMessage.value = data.error_message || null;
                
            } catch (err) {
                console.error(err);
                error.value = 'Failed to load exercises.';
            } finally {
                loading.value = false;
            }
        };

        const markAsValidated = async (exercise: Exercise) => {
            // Only mark as validated if it's a draft and not currently generating
            if (exercise.is_draft && exercise.draft_notes !== 'Generating content...') {
                try {
                    // Optimistic update
                    const originalState = exercise.is_draft;
                    exercise.is_draft = false; 
                    
                    const response = await csrfFetch(`/teacher/authoring-assistant/exercises/${exercise.id}/approve/`, { 
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });

                    if (!response.ok) {
                        exercise.is_draft = originalState; // Revert
                        throw new Error('Failed to update status');                    
                    }
                    
                    const data = await response.json();
                    exercise.is_draft = data.is_draft;
                    exercise.draft_notes = ""; // Clear notes on success locally too
                    
                } catch (err) {
                    alert('Error updating exercise status');
                    console.error(err);
                }
            }
        };

        onMounted(() => {
            fetchExercises();
            refreshInterval.value = window.setInterval(fetchExercises, 3000);
        });

        onUnmounted(() => {
            if (refreshInterval.value) clearInterval(refreshInterval.value);
        });

            return {
            exercises,
            loading,
            sessionStatus,
            coursePk,
            messageToTeacher,
            errorsToTeacher,
            errorMessage,
            allExercisesReady,
            isProcessing,
            hasError,
            markAsValidated,
            error
        };
    }
});

// Mount the app
document.addEventListener('DOMContentLoaded', () => {
    const appContainer = document.getElementById('review-app');
    if (appContainer) {
        const app = createApp(ReviewApp);
        app.config.compilerOptions.delimiters = ['[[', ']]'];
        app.mount(appContainer);
    }
});

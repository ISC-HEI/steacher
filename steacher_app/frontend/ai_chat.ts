import { createApp, defineComponent } from 'vue';
import { ChatbotPanel } from './ChatbotPanel.js';
import { csrfFetch, getCsrfToken } from './utils.js';

interface ThreadSummary {
    id: number;
    title: string;
    created_at: string;
    updated_at: string;
}

interface ThreadDetail extends ThreadSummary {
    messages: Array<{ role: 'user' | 'assistant'; content: string; created_at?: string }>;
}

interface ChatState {
    threads: ThreadSummary[];
    selectedThreadId: number | null;
    selectedThread: ThreadDetail | null;
    loading: boolean;
    courseOptions: { id: number; name: string }[];
    selectedCourseId: number | null;
    defaultThreadId: number | null;
}

document.addEventListener('DOMContentLoaded', () => {
    const el = document.getElementById('ai-chat-app');
    if (!el) return;
    const defaultCourseIdAttr = el.getAttribute('data-default-course-id');
    const defaultCourseId = defaultCourseIdAttr && defaultCourseIdAttr !== '' ? Number(defaultCourseIdAttr) : null;
    const defaultThreadIdAttr = el.getAttribute('data-default-thread-id');
    const defaultThreadId = defaultThreadIdAttr && defaultThreadIdAttr !== '' ? Number(defaultThreadIdAttr) : null;

    const App = defineComponent({
        delimiters: ['[[', ']]'],
        data(): ChatState {
            return {
                threads: [],
                selectedThreadId: null,
                selectedThread: null,
                loading: false,
                courseOptions: [],
                selectedCourseId: defaultCourseId,
                defaultThreadId: defaultThreadId,
            };
        },
        async mounted() {
            await this.loadCourses();
            await this.loadThreads();
        },
        methods: {
            getCsrf(): string { return getCsrfToken(); },
            async loadCourses() {
                // The select options are server-rendered; we reflect them into courseOptions for display
                const select = document.querySelector<HTMLSelectElement>('select[v-model]') || document.querySelector<HTMLSelectElement>('select');
                this.courseOptions = [];
                if (select) {
                    const options = Array.from(select.options);
                    for (const opt of options) {
                        const id = Number(opt.value);
                        const name = opt.textContent || String(id);
                        if (!Number.isNaN(id)) this.courseOptions.push({ id, name });
                    }
                }
                if (!this.selectedCourseId) {
                    const first = this.courseOptions[0];
                    if (first) this.selectedCourseId = first.id;
                }
            },
            async loadThreads() {
                if (!this.selectedCourseId) {
                    this.threads = [];
                    this.selectedThreadId = null;
                    this.selectedThread = null;
                    return;
                }
                const resp = await fetch(`/exercises/chat/threads/?course_id=${this.selectedCourseId}`);
                const data = await resp.json();
                if (data.status === 'success') {
                    this.threads = data.threads || [];
                    if (this.threads.length && !this.selectedThreadId) {
                        // Try selecting the defaultThreadId if provided and present in this course
                        let toSelect: ThreadSummary | null = null;
                        if (this.defaultThreadId) {
                            toSelect = this.threads.find(t => t.id === this.defaultThreadId) || null;
                        }
                        if (!toSelect) toSelect = this.threads[0] || null;
                        if (toSelect) await this.selectThread(toSelect.id);
                        // Clear default after first use
                        this.defaultThreadId = null;
                    }
                }
            },
            async selectThread(id: number) {
                this.selectedThreadId = id;
                const resp = await fetch(`/exercises/chat/threads/${id}/`);
                const data = await resp.json();
                if (data.status === 'success') {
                    this.selectedThread = data.thread as ThreadDetail;
                    // Hydrate ChatbotPanel with thread messages AFTER panel mounts
                    this.$nextTick(() => {
                        // @ts-ignore
                        const panel = this.$refs.chatbotPanel as any;
                        if (panel) {
                            panel.clearMessages();
                            const msgs = (this.selectedThread?.messages || []) as Array<{ role: 'user' | 'assistant'; content: string; created_at?: string }>;
                            for (const m of msgs) {
                                panel.displayMessage(m);
                            }
                            // Keep typing flow fast: focus the input after rendering
                            setTimeout(() => {
                                // @ts-ignore
                                const textarea = panel.$el ? panel.$el.querySelector('textarea') as HTMLTextAreaElement | null : null;
                                if (textarea) textarea.focus();
                            }, 0);
                        }
                    });
                }
            },
            async createThread() {
                this.loading = true;
                try {
                    const resp = await csrfFetch('/exercises/chat/threads/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ title: 'New Chat', course_id: this.selectedCourseId }),
                    });
                    const data = await resp.json();
                    if (data.status === 'success') {
                        this.threads.unshift(data.thread);
                        await this.selectThread(data.thread.id);
                    } else {
                        console.error('Create thread error:', data);
                        alert(data.message || 'Could not create chat.');
                    }
                } catch (err) {
                    console.error('Create thread failed:', err);
                    alert('Failed to create chat. Please try again.');
                } finally {
                    this.loading = false;
                }
            },
            async confirmDelete(t: ThreadSummary) {
                const ok = window.confirm('Really delete this conversation?');
                if (!ok) return;
                await this.deleteThread(t.id);
            },
            async deleteThread(id: number) {
                this.loading = true;
                try {
                    const resp = await csrfFetch(`/exercises/chat/threads/${id}/delete/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                    });
                    const data = await resp.json();
                    if (data.status === 'success') {
                        const idx = this.threads.findIndex(t => t.id === id);
                        if (idx !== -1) this.threads.splice(idx, 1);
                        if (this.selectedThreadId === id) {
                            this.selectedThreadId = null;
                            this.selectedThread = null;
                        }
                    }
                } finally {
                    this.loading = false;
                }
            },
            async handleAsk(message: string) {
                if (!this.selectedThreadId) return;
                this.loading = true;
                try {
                    const resp = await csrfFetch(`/exercises/chat/threads/${this.selectedThreadId}/send/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ message }),
                    });
                    const data = await resp.json();
                    if (data.status === 'success') {
                        // update list ordering/title
                        const idx = this.threads.findIndex(t => t.id === data.thread.id);
                        if (idx !== -1) this.threads.splice(idx, 1);
                        this.threads.unshift({
                            id: data.thread.id,
                            title: data.thread.title,
                            created_at: data.thread.created_at,
                            updated_at: data.thread.updated_at,
                        });
                        // Re-fetch the full thread so the UI shows the complete history
                        await this.selectThread(data.thread.id);
                        // Focus input for next question after assistant reply
                        this.$nextTick(() => {
                            // @ts-ignore
                            const panel = this.$refs.chatbotPanel as any;
                            if (panel && panel.$el) {
                                const textarea = panel.$el.querySelector('textarea') as HTMLTextAreaElement | null;
                                if (textarea) textarea.focus();
                            }
                        });
                    } else {
                        console.error('Send message error:', data);
                        alert(data.message || 'Could not send message.');
                    }
                } catch (err) {
                    console.error('Send message failed:', err);
                    alert('Failed to send message. Please check your connection and try again.');
                } finally {
                    this.loading = false;
                }
            },
        },
        components: {
            'chatbot-panel': ChatbotPanel,
        },
    });

    createApp(App).mount('#ai-chat-app');
});



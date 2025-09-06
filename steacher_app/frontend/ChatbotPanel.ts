import { marked } from 'marked';
import DOMPurify from 'dompurify';
import confetti from 'canvas-confetti';
import { getCsrfToken } from './utils.js';

interface OptionButton {
    id: string;
    title: string;
    comment?: string;
    to?: string;
}

interface ProcessedMessage {
    cleanedContent: string;
    buttons: OptionButton[];
    [key: string]: any;
}

export const ChatbotPanel = {
  props: {
    loading: {  // used to disable the question input field while loading
      type: Boolean,
      default: false,
    },
    attemptId: {
        type: Number,
        default: null,
    },
    // We need to know if there's a next exercise to determine
    // whether to show the course completion celebration.
    nextExerciseUrl: {
        type: String,
        default: '',
    }
  },
  // language=HTML
  template: `
    <div id="chatbot" ref="chatContainer">
      <div class="chat-content" ref="messagesContainer">
        <!-- Chatbot Content. A list of messages exchanged between the user and the assistant. -->
        <div>
          <template v-for="(message, index) in processedMessages">
            <div v-if="message.role === 'user' && message.content"
                 v-html="renderMarkdown(formatUserMessage(message))"
                 class="box content mb-3 user-message"
                 :key="'user-' + index"></div>

            <template v-if="message.role === 'assistant'">
                <div v-if="message.cleanedContent"
                     v-html="renderMarkdown(message.cleanedContent)"
                     class="box content mb-3 assistant-message"
                     :key="'assistant-content-' + index">
                </div>
                <div v-if="message.buttons.length > 0" class="mb-3" :key="'assistant-buttons-' + index">
                    <div v-for="button in message.buttons" :key="button.id" class="mb-2">
                        <button @click="selectOption(button)" class="button is-success is-light">
                            {{ button.title }}
                        </button>
                        <p class="help has-text-centered" v-if="button.comment">{{ button.comment }}</p>
                    </div>
                </div>
            </template>
          </template>
        </div>

        <!-- Pathway Recommendation UI (scrolls with messages) -->
        <div v-if="pathwayLoading" class="pathway-loading box">
          <div class="typing-indicator" aria-label="Assistant is thinking">
            <span class="dot" style="--ti-delay: 0ms;"></span>
            <span class="dot" style="--ti-delay: 150ms;"></span>
            <span class="dot" style="--ti-delay: 300ms;"></span>
            <span class="helper-text has-text-danger">Recommending next exercise... Hold on!</span>
          </div>
        </div>

        <div v-if="pathwayData" class="pathway-recommendation box">
          <!-- Performance Feedback -->
          <div class="feedback-section content">
              <p v-if="pathwayData.performance_feedback.what_went_well">
                  <strong>What Went Well:</strong> {{ pathwayData.performance_feedback.what_went_well }}
              </p>
              <p v-if="pathwayData.performance_feedback.key_learnings">
                  <strong>Key Learnings:</strong> {{ pathwayData.performance_feedback.key_learnings }}
              </p>
          </div>
          <hr>
          <!-- Main Recommendation -->
          <div class="recommendation-card main-recommendation">
              <h3 class="title is-5">Recommended Next Step</h3>
              <p><strong><a :href="getExerciseUrl(pathwayData.main_recommendation.exercise_id)">{{ pathwayData.main_recommendation.title }}</a></strong></p>
              <p class="is-size-7"><em>{{ pathwayData.main_recommendation.what_it_is_about }}</em></p>
              <p class="is-size-7 has-text-weight-semibold">{{ pathwayData.main_recommendation.why_you_should_do_it }}</p>
              <a :href="getExerciseUrl(pathwayData.main_recommendation.exercise_id)" class="button is-primary is-fullwidth mt-2">Start This Exercise</a>
          </div>
          <hr>
          <!-- Alternatives -->
          <div class="alternatives-section">
              <h3 class="title is-5">Other exercises to explore</h3>
              <div class="alternative-recommendations mt-3">
                  <div v-for="alt in pathwayData.alternatives" :key="alt.exercise_id" class="recommendation-card">
                      <p><strong><a :href="getExerciseUrl(alt.exercise_id)">{{ alt.title }}</a></strong></p>
                      <p class="is-size-7"><em>{{ alt.what_it_is_about }}</em></p>
                      <p class="is-size-7 has-text-weight-semibold">{{ alt.why_you_should_do_it }}</p>
                      <a :href="getExerciseUrl(alt.exercise_id)" class="button is-success is-light is-fullwidth is-small mt-2">Try this one</a>
                  </div>
              </div>
          </div>
        </div>

        <!-- Typing indicator (while waiting for AI) - scrolls with content -->
        <div v-if="loading" style="margin-bottom: 0.75rem;">
          <div class="typing-indicator" aria-label="Assistant is thinking">
            <span class="dot" style="--ti-delay: 0ms;"></span>
            <span class="dot" style="--ti-delay: 150ms;"></span>
            <span class="dot" style="--ti-delay: 300ms;"></span>
            <span class="helper-text">Generating feedback...</span>
          </div>
        </div>

        <!-- Jump to latest button -->
        <button v-if="showJumpToLatest"
                class="button is-light is-small jump-to-latest"
                title="Jump to latest"
                @click="handleJumpToLatest">
          <span class="icon"><i class="fas fa-angle-down"></i></span>
        </button>
      </div>

      <!-- Input area -->
      <div class="field has-addons mt-3">
        <!-- Single Input Field -->
        <p class="control is-expanded">
          <textarea
              class="textarea"
              v-model="question"
              placeholder="Enter your message (Shift+Enter for newline)"
              rows="1"
              :disabled="loading || pathwayLoading || pathwayData"
              @keydown="handleKeydown"
              @input="autosizeTextarea"
              style="resize: none; max-height: 40vh"
          ></textarea>
        </p>

        <!-- Ask Question Button -->
        <p class="control">
          <button class="button is-info" @click="askQuestion" :disabled="loading || pathwayLoading || pathwayData">
            <span class="icon">
              <i class="fas fa-question-circle"></i>
            </span>
            <span>Ask Question</span>
          </button>
        </p>

      </div>

       <!-- Course Completion Modal -->
        <div class="modal" :class="{ 'is-active': showCompletionModal }">
          <div class="modal-background" @click="showCompletionModal = false"></div>
          <div class="modal-content has-text-centered" style="position: relative;">
            <button
                aria-label="close"
                @click="showCompletionModal = false"
                style="position: absolute; top: 0.5rem; right: 0.5rem; border: none; background: transparent; color: black; cursor: pointer;"
                title="Close"
            >
                <span class="icon is-large"><i class="fas fa-times"></i></span>
            </button>
            <div class="box">
                <p class="is-size-1">🏆 🎉 🥳</p>
                <h2 class="title">Course Complete!</h2>
                <p class="subtitle">Congratulations on finishing all the exercises in this course!</p>
                <a href="/exercises/dashboard/" class="button is-primary">Back to Dashboard</a>
            </div>
          </div>
        </div>

    </div>
  `,
  data() {
    return {
      question: '',
      internalMessages: [], // Panel-managed messages when no external messages are provided
      pathwayLoading: false,
      pathwayData: null,
      showCompletionModal: false,
      showJumpToLatest: false,
    };
  },
  computed: {
    processedMessages(): ProcessedMessage[] {
      // Parse the message content for buttons, using a regex.
      // @ts-ignore
      return this.internalMessages.map(message => {
        if (message.role === 'assistant') {
          // @ts-ignore
          const processed = this.parseMessageContent(message);
          return processed;
        }
        return { ...message, cleanedContent: message.content, buttons: [] };
      });
    }
  },
  mounted(this: any) {
    this.$nextTick(() => {
      const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
      if (messagesEl) {
        messagesEl.addEventListener('scroll', this.onMessagesScroll, { passive: true });
        // Initial scroll to bottom on mount
        this.scrollToBottom();
      }
    });
  },
  watch: {
    processedMessages: {
      handler(this: any) {
        // After messages update, auto-scroll only if user is near bottom
        this.$nextTick(() => {
          const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
          if (!messagesEl) return;
          if (this.isNearBottom(messagesEl)) {
            this.scrollToBottom();
          } else {
            this.showJumpToLatest = true;
          }
        });
      },
      deep: true
    },
    pathwayLoading(this: any) {
      // Keep scroll behavior consistent when the loading indicator appears/disappears
      this.$nextTick(() => {
        const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
        if (!messagesEl) return;
        if (this.isNearBottom(messagesEl)) {
          this.scrollToBottom();
        } else {
          this.showJumpToLatest = true;
        }
      });
    },
    pathwayData(this: any) {
      // When recommendations load, optionally stick to bottom
      this.$nextTick(() => {
        const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
        if (!messagesEl) return;
        if (this.isNearBottom(messagesEl)) {
          this.scrollToBottom();
        } else {
          this.showJumpToLatest = true;
        }
      });
    }
  },
  methods: {
    clearMessages(this: any) {
      this.internalMessages = [];
      this.showJumpToLatest = false;
      this.$nextTick(() => this.scrollToBottom());
    },
    displayMessage(message: any) {
        const isComplete = message.role === 'assistant' && message.content.includes('<exercise_completed>');

        // Always clean the tag from the message before displaying it
        const messageToDisplay = isComplete
            ? { ...message, content: message.content.replace('<exercise_completed>', '').trim() }
            : message;
        // Push only to internal state. External consumers should manage their own list.
        // @ts-ignore
        this.internalMessages.push(messageToDisplay);

        if (isComplete) {
            // @ts-ignore
            if (this.pathwayData || this.pathwayLoading) {
                return; // A recommendation is already loaded/loading. Do not fire confetti or re-trigger.
            }

            // If we reach here, it's the first time processing completion.
            // Fire confetti and log for debugging.
            console.log('Exercise complete: Firing confetti! 🎊');
            confetti({ particleCount: 200, spread: 150, origin: { y: 0.6 } });

            // Trigger pathway logic
            // @ts-ignore
            if (this.nextExerciseUrl) {
                // @ts-ignore
                this.fetchPathwayRecommendation();
            } else {
                // This is the last exercise, show celebration
                // @ts-ignore
                this.showCompletionModal = true;
            }
        }
    },

    displayRecommendation(pathwayData: any) {
        // Public method to show pre-existing pathway data on page load
        if (pathwayData) {
            // @ts-ignore
            this.pathwayData = pathwayData;
        }
    },

    async fetchPathwayRecommendation() {
        // @ts-ignore
        if (!this.attemptId) {
            return; // Not available in generic chat contexts
        }
        // @ts-ignore
        this.pathwayLoading = true;
        try {
            // @ts-ignore
            const response = await fetch(`/exercises/api/attempts/${this.attemptId}/recommend_pathway/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
            });
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            const result = await response.json();
            if (result.status === 'success') {
                // @ts-ignore
                this.pathwayData = result.data;
            } else {
                console.error('Failed to get pathway recommendation:', result.message);
            }
        } catch (error) {
            console.error('Error fetching pathway recommendation:', error);
        } finally {
            // @ts-ignore
            this.pathwayLoading = false;
        }
    },

    getExerciseUrl(exerciseId: number) {
        return `/exercises/${exerciseId}/`;
    },

    onMessagesScroll(this: any) {
      const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
      if (!messagesEl) return;
      this.showJumpToLatest = !this.isNearBottom(messagesEl);
    },

    isNearBottom(container: HTMLElement, threshold = 80) {
      const distanceFromBottom = container.scrollHeight - (container.scrollTop + container.clientHeight);
      return distanceFromBottom <= threshold;
    },

    scrollToBottom(this: any) {
      const messagesEl = this.$refs.messagesContainer as HTMLElement | undefined;
      if (!messagesEl) return;
      messagesEl.scrollTop = messagesEl.scrollHeight;
      this.showJumpToLatest = false;
    },

    handleJumpToLatest(this: any) {
      this.scrollToBottom();
    },

    autosizeTextarea(event: Event) {
      const textarea = event.target as HTMLTextAreaElement;
      // Reset height to auto to ensure the textarea shrinks when text is deleted
      textarea.style.height = 'auto';
      // Set the height to the scroll height to fit the content
      textarea.style.height = `${textarea.scrollHeight}px`;
    },
    parseMessageContent(message: any): ProcessedMessage {
        // Parse the message content for buttons, using a regex.
        // The regex is a bit complex, but it's the only way to parse the message content for buttons.
        // It's a bit of a hack, but it works.
        const content = message.content || '';
        const buttonRegex = /<button\s+id="([^"]+)"\s+title="([^"]+)"(?:\s+comment="([^"]*)")?(?:\s+to="([^"]*)")?\s*\/>/g;
        const buttons: OptionButton[] = [];
        let match;

        while ((match = buttonRegex.exec(content)) !== null) {
            // TS compiler correctly identifies that these can be undefined.
            // Even though our regex makes them mandatory, it's safer to check.
            const id = match[1];
            const title = match[2];

            if (id && title) {
                console.log('[ChatbotPanel] Found button:', id, title, match[3], match[4]);
                buttons.push({
                    id,
                    title,
                    comment: match[3] || '',
                    to: match[4] || '',
                });
            }
        }

        const cleanedContent = content.replace(buttonRegex, '').trim();

        return { ...message, cleanedContent, buttons };
    },

    selectOption(button: OptionButton) {
        console.log('[ChatbotPanel] Option selected:', button);
        // @ts-ignore
        this.$emit('option-selected', button);
    },

    formatUserMessage(message: any) {
        // Display the user messages differently depending on the action. Add icons to the messages.
        if (!message.metadata || !message.metadata.action) {
            return message.content;
        }

        const { action, code, question, error_message } = message.metadata;

        if (action === 'ask_hint') {
            return '<span class="icon"><i class="fas fa-lightbulb"></i></span> _Hint requested_';
        }

        else if (action === 'ask_question') {
            return '<span class="icon"><i class="fas fa-question-circle"></i></span> ' + (question || 'Question asked');
        }

        else if (action === 'run_submission') {
            // Collapsible block for any submission (Python/SQL)
            let detailsContent = message.content || '';
            if (!detailsContent && code) {
                const errorSection = error_message ? `\n\nError:\n\n\`${error_message}\`` : '';
                detailsContent = `\n\n\`\`\`\n${code}\n\`\`\`\n${errorSection}`;
            }
            const renderedDetailsContent = this.renderMarkdown(detailsContent);
            return `
<details class="collapsible-message">
  <summary><span class="icon ml-3"><i class="fas fa-code"></i></span> Code submitted to AI tutor</summary>
  <div class="mt-2">${renderedDetailsContent}</div>
  </details>`;
        }

        else if (action === 'submit_answer') {
            // Collapsible block for open-question free-form answers
            const plainAnswer = (message.metadata && typeof message.metadata.answer === 'string') ? message.metadata.answer : '';
            const detailsContent = (message.content && String(message.content).trim()) || plainAnswer || '';
            const renderedDetailsContent = this.renderMarkdown(detailsContent);
            return `
<details class="collapsible-message">
  <summary><span class="icon ml-3"><i class="fas fa-comment-dots"></i></span> Answer submitted</summary>
  <div class="mt-2">${renderedDetailsContent}</div>
  </details>`;
        }

        else if (action === 'option_selected') {
            return '<span class="icon"><i class="fas fa-check-circle"></i></span> ' + (message.metadata.selected_option.title || 'Option selected');
        }

        return message.content; // Fallback
    },
    askQuestion(this: any) {
      // Emit an event to the parent component
      if (this.question.trim()) {
        const userQuestion = this.question.trim();
        this.$emit('question-asked', userQuestion);

        // Clear the input field after asking the question
        this.question = '';

        // Reset textarea height on next tick after clearing the content
        this.$nextTick(() => {
          const textarea = this.$el.querySelector('textarea');
          if (textarea) {
            textarea.style.height = 'auto';
          }
        });
      }
    },
    handleKeydown(this: any, event: KeyboardEvent) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        this.askQuestion();
      }
      // If Shift+Enter, let the default behavior insert a newline
    },
    renderMarkdown(this: any, content: string) {
      if (!content) return '';
      // Sanitize the content to prevent XSS attacks, then parse Markdown
      return DOMPurify.sanitize(marked.parse(content) as string);
    }
  }
}; 
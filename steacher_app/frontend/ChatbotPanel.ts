import { marked } from 'marked';
import DOMPurify from 'dompurify';

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
    messages: {
      type: Array,
      default: () => []
    },
    loading: {  // used to disable the question input field while loading
      type: Boolean,
      default: false,
    }
  },
  // language=HTML
  template: `
    <div id="chatbot" ref="chatContainer">
      <div class="chat-content">
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
                        <button @click="selectOption(button)" class="button is-info is-fullwidth">
                            {{ button.title }}
                        </button>
                        <p class="help has-text-centered" v-if="button.comment">{{ button.comment }}</p>
                    </div>
                </div>
            </template>
          </template>
        </div>
      </div>

      <!-- Typing indicator (while waiting for AI) -->
      <div v-if="loading" style="margin-bottom: 0.75rem;">
        <div class="typing-indicator" aria-label="Assistant is thinking">
          <span class="dot" style="--ti-delay: 0ms;"></span>
          <span class="dot" style="--ti-delay: 150ms;"></span>
          <span class="dot" style="--ti-delay: 300ms;"></span>
          <span class="helper-text">Generating feedback...</span>
        </div>
      </div>

      <!-- Input area -->
      <div class="field has-addons mt-3">
        <!-- Single Input Field -->
        <p class="control is-expanded">
          <textarea
              class="textarea"
              v-model="question"
              placeholder="Enter your message (Shift+Enter for newline)"
              rows="3"
              :disabled="loading"
              @keydown="handleKeydown"
          ></textarea>
        </p>

        <!-- Ask Question Button -->
        <p class="control">
          <button class="button is-info" @click="askQuestion" :disabled="loading">
            <span class="icon">
              <i class="fas fa-question-circle"></i>
            </span>
            <span>Ask Question</span>
          </button>
        </p>

      </div>
    </div>
  `,
  data() {
    return {
      question: '',
    };
  },
  computed: {
    processedMessages(): ProcessedMessage[] {
      // Parse the message content for buttons, using a regex.
      // @ts-ignore
      return this.messages.map(message => {
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
  },
  watch: {
    messages: {
      handler(this: any) {
        // Use nextTick to wait for the DOM to update
        this.$nextTick(() => {
          const container = this.$refs.chatContainer as HTMLElement;
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
        });
      },
      deep: true // Watch for changes inside the array
    }
  },
  methods: {
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
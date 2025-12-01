// Centralized Markdown and LaTeX rendering utilities

import { marked } from 'marked';
import DOMPurify from 'dompurify';
import katex from 'katex';

/**
 * Renders Markdown content with optional KaTeX math support.
 * 
 * @param content - The raw Markdown text to render
 * @param enableMath - Whether to process LaTeX math expressions (default: true)
 * @returns Sanitized HTML string with rendered Markdown and math
 */
export function renderMarkdown(content: string, enableMath: boolean = true): string {
    if (!content) return '';
    
    // Strip "Guidance Text:" prefix if present
    let cleanContent = content.replace(/^Guidance Text:\s*/i, '').trim();
    
    // Parse Markdown
    let html = marked.parse(cleanContent) as string;
    
    // Sanitize HTML to prevent XSS attacks
    html = DOMPurify.sanitize(html);
    
    // Process KaTeX math expressions if enabled
    if (enableMath) {
        html = renderMathInHtml(html);
    }
    
    return html;
}

/**
 * Processes KaTeX math expressions in HTML content.
 * Handles both display math ($$...$$) and inline math ($...$).
 * 
 * @param html - HTML content containing math expressions
 * @returns HTML with rendered math expressions
 */
export function renderMathInHtml(html: string): string {
    try {
        // Display math $$...$$
        html = html.replace(/\$\$([^$]+)\$\$/g, (match, math) => {
            try {
                return katex.renderToString(math, { 
                    displayMode: true,
                    strict: false,
                    trust: false
                });
            } catch (e) {
                console.error('KaTeX display math error:', e);
                return match;
            }
        });

        // Inline math $...$ (negative lookbehind/lookahead to avoid matching $$)
        html = html.replace(/(?<!\$)\$([^$\n]+)\$(?!\$)/g, (match, math) => {
            try {
                return katex.renderToString(math, { 
                    displayMode: false,
                    strict: false,
                    trust: false
                });
            } catch (e) {
                console.error('KaTeX inline math error:', e);
                return match;
            }
        });
    } catch (e) {
        console.error('Error processing math:', e);
    }

    return html;
}


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
    
    // Process KaTeX math expressions if enabled
    if (enableMath) {
        // Protect math blocks to prevent Markdown parser from messing up LaTeX (e.g. backslashes)
        const mathBlocks: { type: 'display' | 'inline', content: string }[] = [];
        
        // Replace display math $$...$$
        // We use a specific placeholder that Markdown is likely to treat as a paragraph or text, 
        // which we'll unwrap later if needed.
        cleanContent = cleanContent.replace(/\$\$([\s\S]+?)\$\$/g, (match, math) => {
            const id = mathBlocks.length;
            mathBlocks.push({ type: 'display', content: math });
            return `%%%MATH_BLOCK_${id}%%%`;
        });
        
        // Replace inline math $...$
        // Negative lookbehind/lookahead to avoid matching $$
        cleanContent = cleanContent.replace(/(?<!\$)\$([^$\n]+?)\$(?!\$)/g, (match, math) => {
            const id = mathBlocks.length;
            mathBlocks.push({ type: 'inline', content: math });
            return `%%%MATH_INLINE_${id}%%%`;
        });
        
        // Parse Markdown
        let html = marked.parse(cleanContent) as string;
        
        // Sanitize HTML to prevent XSS attacks
        html = DOMPurify.sanitize(html);
        
        // Restore and render math
        // Handle block math - potentially unwrapping from <p>
        html = html.replace(/(?:<p>\s*)?%%%MATH_BLOCK_(\d+)%%%(?:\s*<\/p>)?/g, (match, id) => {
            const block = mathBlocks[parseInt(id)];
            if (!block) return match;
            try {
                return katex.renderToString(block.content, { 
                    displayMode: true,
                    strict: false,
                    trust: false
                });
            } catch (e) {
                console.error('KaTeX display math error:', e);
                return `$$${block.content}$$`;
            }
        });
        
        // Handle inline math
        html = html.replace(/%%%MATH_INLINE_(\d+)%%%/g, (match, id) => {
            const block = mathBlocks[parseInt(id)];
            if (!block) return match;
            try {
                return katex.renderToString(block.content, { 
                    displayMode: false,
                    strict: false,
                    trust: false
                });
            } catch (e) {
                console.error('KaTeX inline math error:', e);
                return `$${block.content}$`;
            }
        });

        return html;
    }
    
    // Default path without math
    let html = marked.parse(cleanContent) as string;
    return DOMPurify.sanitize(html);
}


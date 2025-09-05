export function getCsrfToken(): string {
    const input = document.querySelector<HTMLInputElement>('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;

    const meta = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;

    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    if (match) return decodeURIComponent(match[1]!);

    throw new Error('CSRF token not found');
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE']);

export async function csrfFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    const method = (init.method || 'GET').toUpperCase();
    const headers = new Headers(init.headers || {});
    if (!SAFE_METHODS.has(method)) {
        if (!headers.has('X-CSRFToken')) {
            headers.set('X-CSRFToken', getCsrfToken());
        }
    }
    return fetch(input, { ...init, headers });
}



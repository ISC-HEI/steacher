// Dedicated module worker for running Pyodide code with stdout capture
// Communication protocol:
// - From main: { type: 'init', pyodideModuleUrl: string, indexURL: string }
// - From worker: { type: 'ready' }
// - From main: { type: 'run', runId: string, code: string, stdoutLimit?: number }
// - From worker: { type: 'result', runId: string, success: boolean, stdout?: string, error?: string }

// Note: We intentionally avoid importing from the main bundle to keep the worker self-contained.

export interface InitMessage {
    type: 'init';
    pyodideModuleUrl: string;
    indexURL?: string;
}

export interface RunMessage {
    type: 'run';
    runId: string;
    code: string;
    stdoutLimit?: number;
}

type InMessage = InitMessage | RunMessage;

interface ResultMessage {
    type: 'result';
    runId: string;
    success: boolean;
    stdout?: string;
    error?: string;
}

interface ReadyMessage {
    type: 'ready';
}

interface InitErrorMessage {
    type: 'init-error';
    error: string;
}

let pyodide: any | null = null;
let isInitializing = false;

function formatPyodideErrorString(error: string): string {
    try {
        if (!error) return 'Unknown error';
        const normalized = error.replace(/\r\n/g, '\n');
        const lines = normalized.split('\n');
        const fileExecRegex = /^\s*File\s+"<exec>",\s+line\s+\d+/;
        let anchorIndex = -1;
        for (let i = lines.length - 1; i >= 0; i--) {
            const line = lines[i] ?? '';
            if (fileExecRegex.test(line)) {
                anchorIndex = i;
                break;
            }
        }
        if (anchorIndex !== -1) {
            const snippet = lines.slice(anchorIndex).join('\n').trim();
            return snippet || error.trim();
        }
        const tracebackIndex = lines.findIndex(l => l.includes('Traceback (most recent call last):'));
        if (tracebackIndex !== -1) {
            const tail = lines.slice(Math.max(lines.length - 6, tracebackIndex)).join('\n').trim();
            return tail || error.trim();
        }
        return error.trim();
    } catch (_) {
        return String(error || 'Unknown error');
    }
}

function dirFromUrl(url: string): string {
    try {
        const u = new URL(url, (self as any).location?.href || undefined);
        const parts = u.pathname.split('/');
        parts.pop();
        u.pathname = parts.join('/') + '/';
        u.search = '';
        u.hash = '';
        return u.toString();
    } catch (_) {
        // Fallback: strip filename by last '/'
        const idx = url.lastIndexOf('/');
        return (idx >= 0 ? url.slice(0, idx + 1) : url) + '';
    }
}

async function ensurePyodideLoaded(pyodideModuleUrl: string, indexURL?: string): Promise<void> {
    if (pyodide || isInitializing) {
        // If already loaded or in progress, just wait until available
        while (isInitializing && !pyodide) {
            // simple spin-wait with micro-sleeps
            // eslint-disable-next-line no-await-in-loop
            await new Promise((r) => setTimeout(r, 10));
        }
        return;
    }
    isInitializing = true;
    try {
        // Debug logs
        // @ts-ignore
        console.log('[python_worker] Importing Pyodide module from', pyodideModuleUrl);
        // Add cache-busting to avoid stale caching issues
        const cacheBust = Date.now();
        const urlWithCb = pyodideModuleUrl.includes('?') ? `${pyodideModuleUrl}&v=${cacheBust}` : `${pyodideModuleUrl}?v=${cacheBust}`;

        let mod: any;
        try {
            mod = await import(urlWithCb as any);
        } catch (e) {
            // @ts-ignore
            console.warn('[python_worker] Failed to import local Pyodide module, falling back to CDN', e);
            // Fallback to matching CDN version of Pyodide
            // Note: keep version in sync with package.json
            const cdnUrl = `https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs?v=${cacheBust}`;
            mod = await import(cdnUrl as any);
            // If we used CDN, indexURL should point to the CDN base
            if (!indexURL || indexURL.length === 0) {
                indexURL = 'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';
            }
        }
        const effectiveIndex = indexURL && indexURL.length > 0 ? indexURL : dirFromUrl(pyodideModuleUrl);
        // @ts-ignore
        console.log('[python_worker] Calling loadPyodide with indexURL =', effectiveIndex);
        pyodide = await mod.loadPyodide({ indexURL: effectiveIndex });
        // @ts-ignore
        console.log('[python_worker] Pyodide loaded');
    } finally {
        isInitializing = false;
    }
}

function postReady() {
    const msg: ReadyMessage = { type: 'ready' };
    // @ts-ignore - self is WorkerGlobalScope
    self.postMessage(msg);
}

function postResult(result: ResultMessage) {
    // @ts-ignore
    self.postMessage(result);
}

function postInitError(e: unknown) {
    const msg: InitErrorMessage = { type: 'init-error', error: String(e) };
    // @ts-ignore
    self.postMessage(msg);
}

// @ts-ignore - self is WorkerGlobalScope
self.onmessage = async (evt: MessageEvent<InMessage>) => {
    const data = evt.data;
    if (!data) return;

    if (data.type === 'init') {
        try {
            // @ts-ignore
            console.log('[python_worker] Received init message');
            await ensurePyodideLoaded(data.pyodideModuleUrl, data.indexURL);
            postReady();
        } catch (e) {
            // @ts-ignore
            console.error('[python_worker] Init error', e);
            postInitError(e);
        }
        return;
    }

    if (data.type === 'run') {
        const { runId, code, stdoutLimit = 100_000 } = data;
        if (!pyodide) {
            postResult({ type: 'result', runId, success: false, error: 'Pyodide not initialized' });
            return;
        }

        let capturedStdout = '';
        const appendStdout = (msg: string) => {
            if (capturedStdout.length >= stdoutLimit) return;
            const remaining = stdoutLimit - capturedStdout.length;
            if (msg.length <= remaining) {
                capturedStdout += msg;
            } else {
                capturedStdout += msg.slice(0, Math.max(0, remaining));
                capturedStdout += '\n... [truncated]\n';
            }
        };

        try {
            // @ts-ignore
            console.log('[python_worker] Starting run', runId);
            pyodide.setStdout({
                batched: (msg: string) => {
                    appendStdout(msg + '\n');
                },
            });
            // Some errors print to stderr only; reflect them in the same buffer
            pyodide.setStderr({
                batched: (msg: string) => {
                    appendStdout(msg + '\n');
                },
            });

            await pyodide.loadPackagesFromImports(code);
            await pyodide.runPythonAsync(code);
            postResult({ type: 'result', runId, success: true, stdout: capturedStdout.trim() });
        } catch (e) {
            // @ts-ignore
            console.error('[python_worker] Run error', e);
            const raw = (e && (e as any).message) ? String((e as any).message) : String(e);
            const formatted = formatPyodideErrorString(raw);
            postResult({ type: 'result', runId, success: false, error: formatted });
        }
        return;
    }
};



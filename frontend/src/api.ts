import { fetchAuthSession } from 'aws-amplify/auth';

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
    const session = await fetchAuthSession();
    const idToken = session.tokens?.idToken?.toString();
    if (!idToken) {
        throw new Error('Not authenticated');
    }
    return fetch(path, {
        ...init,
        headers: {
            ...init.headers,
            Authorization: `Bearer ${idToken}`,
        },
    });
}

export async function publicApiFetch(path: string, init: RequestInit = {}): Promise<Response> {
    return fetch(path, init);
}

export async function parseDetail(response: Response): Promise<string> {
    try {
        const body = await response.json();
        if (typeof body?.detail === 'string') {
            return body.detail;
        }
        return `${response.status} ${response.statusText}`;
    } catch {
        return `${response.status} ${response.statusText}`;
    }
}

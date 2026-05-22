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

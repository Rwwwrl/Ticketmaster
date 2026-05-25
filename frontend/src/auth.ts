import { useEffect, useState } from 'react';
import { fetchAuthSession, getCurrentUser } from 'aws-amplify/auth';
import { Hub } from 'aws-amplify/utils';

export type AuthStateEnum = 'unknown' | 'signed-in' | 'signed-out';

export interface AuthState {
    authState: AuthStateEnum;
    email: string;
}

async function readEmail(): Promise<string> {
    const session = await fetchAuthSession();
    const payload = session.tokens?.idToken?.payload as Record<string, unknown> | undefined;
    const email = payload?.email;
    return typeof email === 'string' ? email : '';
}

export function useAuth(): AuthState {
    const [authState, setAuthState] = useState<AuthStateEnum>('unknown');
    const [email, setEmail] = useState<string>('');

    useEffect(() => {
        let cancelled = false;
        const detect = async () => {
            try {
                await getCurrentUser();
                const userEmail = await readEmail();
                if (!cancelled) {
                    setAuthState('signed-in');
                    setEmail(userEmail);
                }
            } catch {
                if (!cancelled) {
                    setAuthState('signed-out');
                }
            }
        };
        void detect();

        const unsubscribe = Hub.listen('auth', ({ payload }) => {
            if (payload.event === 'signedIn') {
                void readEmail().then((userEmail) => {
                    if (!cancelled) {
                        setAuthState('signed-in');
                        setEmail(userEmail);
                    }
                });
            } else if (payload.event === 'signedOut') {
                if (!cancelled) {
                    setAuthState('signed-out');
                    setEmail('');
                }
            }
        });

        return () => {
            cancelled = true;
            unsubscribe();
        };
    }, []);

    return { authState, email };
}

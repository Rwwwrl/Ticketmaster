import { useEffect, useState } from 'react';
import { getCurrentUser } from 'aws-amplify/auth';
import { Hub } from 'aws-amplify/utils';

export type AuthStateEnum = 'unknown' | 'signed-in' | 'signed-out';

export interface AuthState {
    authState: AuthStateEnum;
    email: string;
}

export function useAuth(): AuthState {
    const [authState, setAuthState] = useState<AuthStateEnum>('unknown');
    const [email, setEmail] = useState<string>('');

    useEffect(() => {
        getCurrentUser()
            .then((user) => {
                setAuthState('signed-in');
                setEmail(user.signInDetails?.loginId ?? '');
            })
            .catch(() => {
                setAuthState('signed-out');
            });

        return Hub.listen('auth', ({ payload }) => {
            if (payload.event === 'signedIn') {
                getCurrentUser().then((user) => {
                    setAuthState('signed-in');
                    setEmail(user.signInDetails?.loginId ?? '');
                });
            } else if (payload.event === 'signedOut') {
                setAuthState('signed-out');
                setEmail('');
            }
        });
    }, []);

    return { authState, email };
}

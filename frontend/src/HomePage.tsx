import { useEffect, useState } from 'react';
import { signInWithRedirect, signOut, getCurrentUser } from 'aws-amplify/auth';
import { Hub } from 'aws-amplify/utils';
import { apiFetch } from './api';

type AuthStateEnum = 'unknown' | 'signed-in' | 'signed-out';

export function HomePage() {
    const [authState, setAuthState] = useState<AuthStateEnum>('unknown');
    const [email, setEmail] = useState<string>('');
    const [result, setResult] = useState<string>('');
    const [pending, setPending] = useState<boolean>(false);
    const [authError] = useState<boolean>(() => {
        const params = new URLSearchParams(window.location.search);
        return params.get('auth_error') === '1';
    });

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

    const handleSignIn = () => {
        void signInWithRedirect({ provider: 'Google' });
    };

    const handleSignOut = () => {
        void signOut({ global: true });
    };

    const handleHealthcheck = async () => {
        setPending(true);
        setResult('');
        try {
            const response = await fetch('/api/health');
            setResult(`${response.status}: ${await response.text()}`);
        } catch (error) {
            setResult(`error: ${error instanceof Error ? error.message : 'unknown'}`);
        } finally {
            setPending(false);
        }
    };

    const handleMe = async () => {
        setPending(true);
        setResult('');
        try {
            const response = await apiFetch('/api/v1/me/');
            setResult(`${response.status}: ${await response.text()}`);
        } catch (error) {
            setResult(`error: ${error instanceof Error ? error.message : 'unknown'}`);
        } finally {
            setPending(false);
        }
    };

    const handleDelete = async () => {
        if (!window.confirm('This will permanently delete your account. Continue?')) {
            return;
        }
        setPending(true);
        setResult('');
        try {
            const response = await apiFetch('/api/v1/me/', { method: 'DELETE' });
            if (!response.ok) {
                setResult(`Delete failed: ${response.status}`);
                return;
            }
            // Backend already called admin_delete_user. signOut() (no global) just clears the
            // local Amplify token cache — global sign-out would call Cognito's GlobalSignOut
            // and fail since the user no longer exists.
            await signOut();
        } catch (error) {
            setResult(`error: ${error instanceof Error ? error.message : 'unknown'}`);
        } finally {
            setPending(false);
        }
    };

    if (authState === 'unknown') {
        return (
            <main>
                <p>Loading…</p>
            </main>
        );
    }

    return (
        <main>
            <h1>Hello from ticketmaster frontend</h1>
            <p>Built with React + Vite. Deployed via ECS Express.</p>

            {authError && <p role="alert">Sign-in failed. Try again.</p>}

            {authState === 'signed-in' ? (
                <>
                    <p>
                        Signed in as <strong>{email}</strong>
                    </p>
                    <button type="button" onClick={handleSignOut} disabled={pending}>
                        Sign out
                    </button>
                    <button type="button" onClick={handleDelete} disabled={pending}>
                        Delete account
                    </button>
                </>
            ) : (
                <button type="button" onClick={handleSignIn}>
                    Sign in with Google
                </button>
            )}

            <hr />

            <button type="button" onClick={handleHealthcheck} disabled={pending}>
                {pending ? 'Sending…' : 'Send healthcheck'}
            </button>
            <button type="button" onClick={handleMe} disabled={pending}>
                Call /me
            </button>

            {result && <pre>{result}</pre>}
        </main>
    );
}

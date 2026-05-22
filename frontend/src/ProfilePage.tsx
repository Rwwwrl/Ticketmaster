import { useEffect, useState } from 'react';
import { signInWithRedirect, signOut } from 'aws-amplify/auth';
import { apiFetch, parseDetail } from './api';
import { useAuth } from './auth';

interface Me {
    uuid: string;
    pool_id: string;
    email: string;
    cognito_username: string;
    created_at: string;
    updated_at: string;
}

export function ProfilePage() {
    const { authState, email } = useAuth();
    const [me, setMe] = useState<Me | null>(null);
    const [error, setError] = useState<string>('');
    const [pending, setPending] = useState<boolean>(false);

    useEffect(() => {
        if (authState !== 'signed-in') {
            return;
        }
        let cancelled = false;
        const run = async () => {
            setPending(true);
            setError('');
            try {
                const response = await apiFetch('/api/v1/me/');
                if (cancelled) {
                    return;
                }
                if (!response.ok) {
                    setError(await parseDetail(response));
                    return;
                }
                setMe((await response.json()) as Me);
            } catch (err) {
                if (!cancelled) {
                    setError(err instanceof Error ? err.message : 'unknown error');
                }
            } finally {
                if (!cancelled) {
                    setPending(false);
                }
            }
        };
        void run();
        return () => {
            cancelled = true;
        };
    }, [authState]);

    const handleSignIn = () => {
        void signInWithRedirect({ provider: 'Google' });
    };

    const handleSignOut = () => {
        void signOut({ global: true });
    };

    const handleDelete = async () => {
        if (!window.confirm('This will permanently delete your account. Continue?')) {
            return;
        }
        setPending(true);
        setError('');
        try {
            const response = await apiFetch('/api/v1/me/', { method: 'DELETE' });
            if (!response.ok) {
                setError(await parseDetail(response));
                return;
            }
            // Backend already called admin_delete_user. signOut() (no global) just clears the
            // local Amplify token cache — global sign-out would call Cognito's GlobalSignOut
            // and fail since the user no longer exists.
            await signOut();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'unknown error');
        } finally {
            setPending(false);
        }
    };

    if (authState === 'unknown') {
        return <p>Loading…</p>;
    }

    if (authState === 'signed-out') {
        return (
            <section>
                <h1>Profile</h1>
                <p>Sign in to manage your account.</p>
                <button type="button" onClick={handleSignIn}>
                    Sign in with Google
                </button>
            </section>
        );
    }

    return (
        <section>
            <h1>Profile</h1>
            <p>
                Signed in as <strong>{email}</strong>
            </p>
            {pending && !me && <p>Loading…</p>}
            {error && <p className="error">{error}</p>}
            {me && (
                <dl className="profile-details">
                    <dt>Email</dt>
                    <dd>{me.email}</dd>
                    <dt>UUID</dt>
                    <dd>{me.uuid}</dd>
                    <dt>Cognito username</dt>
                    <dd>{me.cognito_username}</dd>
                    <dt>Pool ID</dt>
                    <dd>{me.pool_id}</dd>
                    <dt>Created</dt>
                    <dd>{new Date(me.created_at).toLocaleString()}</dd>
                    <dt>Updated</dt>
                    <dd>{new Date(me.updated_at).toLocaleString()}</dd>
                </dl>
            )}
            <button type="button" onClick={handleSignOut} disabled={pending}>
                Sign out
            </button>{' '}
            <button type="button" onClick={handleDelete} disabled={pending}>
                Delete account
            </button>
        </section>
    );
}

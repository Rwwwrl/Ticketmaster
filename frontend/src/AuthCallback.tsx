import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Hub } from 'aws-amplify/utils';

export function AuthCallback() {
    const navigate = useNavigate();

    useEffect(() => {
        return Hub.listen('auth', ({ payload }) => {
            if (payload.event === 'signedIn') {
                navigate('/', { replace: true });
            } else if (payload.event === 'signInWithRedirect_failure') {
                navigate('/?auth_error=1', { replace: true });
            }
        });
    }, [navigate]);

    return (
        <main>
            <p>Signing you in…</p>
        </main>
    );
}

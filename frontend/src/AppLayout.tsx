import { NavLink, Outlet } from 'react-router-dom';
import { signInWithRedirect } from 'aws-amplify/auth';
import { useAuth } from './auth';

export function AppLayout() {
    const { authState } = useAuth();

    const handleSignIn = () => {
        void signInWithRedirect({ provider: 'Google' });
    };

    return (
        <main>
            <nav className="tabbar">
                <NavLink to="/events" className={({ isActive }) => (isActive ? 'tab active' : 'tab')}>
                    Events
                </NavLink>
                {authState === 'signed-in' && (
                    <NavLink to="/profile" className={({ isActive }) => (isActive ? 'tab active' : 'tab')}>
                        Profile
                    </NavLink>
                )}
                {authState === 'signed-out' && (
                    <button type="button" className="tabbar-action" onClick={handleSignIn}>
                        Sign in
                    </button>
                )}
            </nav>
            <Outlet />
        </main>
    );
}

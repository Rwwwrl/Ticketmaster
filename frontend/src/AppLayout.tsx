import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from './auth';

export function AppLayout() {
    const { authState } = useAuth();

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
            </nav>
            <Outlet />
        </main>
    );
}

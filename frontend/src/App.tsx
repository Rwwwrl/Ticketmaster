import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from './AppLayout';
import { AuthCallback } from './AuthCallback';
import { EventDetailsPage } from './EventDetailsPage';
import { EventsPage } from './EventsPage';
import { ProfilePage } from './ProfilePage';
import './styles.css';

export function App() {
    return (
        <Routes>
            <Route path="/" element={<Navigate to="/events" replace />} />
            <Route element={<AppLayout />}>
                <Route path="/events" element={<EventsPage />} />
                <Route path="/events/:eventId" element={<EventDetailsPage />} />
                <Route path="/profile" element={<ProfilePage />} />
            </Route>
            <Route path="/auth/callback" element={<AuthCallback />} />
        </Routes>
    );
}

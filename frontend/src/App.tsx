import { Routes, Route } from 'react-router-dom';
import { AuthCallback } from './AuthCallback';
import { HomePage } from './HomePage';
import './styles.css';

export function App() {
    return (
        <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
        </Routes>
    );
}

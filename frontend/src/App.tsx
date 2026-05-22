import { useState } from 'react';
import './styles.css';

type HealthResponse = { status: string };

export function App() {
    const [result, setResult] = useState<string>('');
    const [pending, setPending] = useState<boolean>(false);

    const handleHealthcheck = async () => {
        setPending(true);
        setResult('');
        try {
            const response = await fetch('/api/health');
            if (!response.ok) {
                setResult(`HTTP ${response.status}`);
                return;
            }
            const data = (await response.json()) as HealthResponse;
            setResult(JSON.stringify(data));
        } catch (error) {
            setResult(`error: ${error instanceof Error ? error.message : 'unknown'}`);
        } finally {
            setPending(false);
        }
    };

    return (
        <main>
            <h1>Hello from ticketmaster frontend</h1>
            <p>Built with React + Vite. Deployed via ECS Express.</p>
            <button type="button" onClick={handleHealthcheck} disabled={pending}>
                {pending ? 'Sending…' : 'Send healthcheck'}
            </button>
            {result && <pre>{result}</pre>}
        </main>
    );
}

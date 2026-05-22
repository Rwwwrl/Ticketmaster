import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { parseDetail, publicApiFetch } from './api';

interface EventItem {
    id: number;
    name: string;
    description: string;
    type: string;
    start_at: string;
}

interface EventsPageResponse {
    items: EventItem[];
    page_size: number;
    next_cursor: string | null;
}

export function EventsPage() {
    const [items, setItems] = useState<EventItem[]>([]);
    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [pending, setPending] = useState<boolean>(true);
    const [error, setError] = useState<string>('');

    useEffect(() => {
        let cancelled = false;
        const run = async () => {
            try {
                const response = await publicApiFetch('/api/v1/events/');
                if (cancelled) {
                    return;
                }
                if (!response.ok) {
                    setError(await parseDetail(response));
                    return;
                }
                const page = (await response.json()) as EventsPageResponse;
                setItems(page.items);
                setNextCursor(page.next_cursor);
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
    }, []);

    const handleLoadMore = async () => {
        if (!nextCursor) {
            return;
        }
        setPending(true);
        setError('');
        try {
            const response = await publicApiFetch(`/api/v1/events/?cursor=${encodeURIComponent(nextCursor)}`);
            if (!response.ok) {
                setError(await parseDetail(response));
                return;
            }
            const page = (await response.json()) as EventsPageResponse;
            setItems((prev) => [...prev, ...page.items]);
            setNextCursor(page.next_cursor);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'unknown error');
        } finally {
            setPending(false);
        }
    };

    return (
        <section>
            <h1>Events</h1>
            {error && <p className="error">{error}</p>}
            {items.length === 0 && !pending && !error && <p>No events.</p>}
            <ul className="event-list">
                {items.map((event) => (
                    <li key={event.id}>
                        <Link to={`/events/${event.id}`}>
                            <strong>{event.name}</strong>
                            <span className="event-meta">
                                {event.type} · {new Date(event.start_at).toLocaleString()}
                            </span>
                        </Link>
                    </li>
                ))}
            </ul>
            {nextCursor && (
                <button type="button" onClick={() => void handleLoadMore()} disabled={pending}>
                    {pending ? 'Loading…' : 'Load more'}
                </button>
            )}
        </section>
    );
}

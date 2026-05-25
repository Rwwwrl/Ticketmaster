import { type FormEventHandler, useEffect, useState } from 'react';
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

function buildEventsUrl(q: string, cursor: string | null): string {
    if (q) {
        let url = `/api/v1/events/search?q=${encodeURIComponent(q)}`;
        if (cursor) {
            url += `&cursor=${encodeURIComponent(cursor)}`;
        }
        return url;
    }
    if (cursor) {
        return `/api/v1/events/?cursor=${encodeURIComponent(cursor)}`;
    }
    return '/api/v1/events/';
}

export function EventsPage() {
    const [items, setItems] = useState<EventItem[]>([]);
    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [pending, setPending] = useState<boolean>(true);
    const [error, setError] = useState<string>('');
    const [query, setQuery] = useState<string>('');
    const [activeQuery, setActiveQuery] = useState<string>('');

    const fetchEvents = async (q: string, cursor: string | null, append: boolean) => {
        setPending(true);
        setError('');
        try {
            const response = await publicApiFetch(buildEventsUrl(q, cursor));
            if (!response.ok) {
                setError(await parseDetail(response));
                return;
            }
            const page = (await response.json()) as EventsPageResponse;
            setItems((prev) => (append ? [...prev, ...page.items] : page.items));
            setNextCursor(page.next_cursor);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'unknown error');
        } finally {
            setPending(false);
        }
    };

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

    const handleSearch: FormEventHandler<HTMLFormElement> = (event) => {
        event.preventDefault();
        if (pending) {
            return;
        }
        const trimmed = query.trim();
        setActiveQuery(trimmed);
        setNextCursor(null);
        void fetchEvents(trimmed, null, false);
    };

    const handleLoadMore = () => {
        if (!nextCursor) {
            return;
        }
        void fetchEvents(activeQuery, nextCursor, true);
    };

    return (
        <section>
            <h1>Events</h1>
            <form className="search-form" onSubmit={handleSearch}>
                <input
                    type="search"
                    placeholder="Search events…"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                />
                <button type="submit" disabled={pending}>
                    Search
                </button>
            </form>
            {error && <p className="error">{error}</p>}
            {items.length === 0 && !pending && !error && (
                <p>{activeQuery ? 'No events found.' : 'No events.'}</p>
            )}
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
                <button type="button" onClick={handleLoadMore} disabled={pending}>
                    {pending ? 'Loading…' : 'Load more'}
                </button>
            )}
        </section>
    );
}

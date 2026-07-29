import { type FormEventHandler, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { parseDetail, publicApiFetch } from './api';

type SortKey = 'start_at' | 'price';

interface EventItem {
    id: number;
    name: string;
    description: string;
    type: string;
    start_at: string;
    price: number;
    currency: string;
}

interface EventsPageResponse {
    items: EventItem[];
    page_size: number;
    next_cursor: string | null;
}

function buildEventsUrl(q: string, cursor: string | null, sortBy: SortKey): string {
    if (q) {
        // NOTE: search is rank-ordered, so sort_key does not apply here.
        let url = `/api/v1/events/search?q=${encodeURIComponent(q)}`;
        if (cursor) {
            url += `&cursor=${encodeURIComponent(cursor)}`;
        }
        return url;
    }
    const params = new URLSearchParams({ sort_key: sortBy, page_size: '50' });
    if (cursor) {
        params.set('cursor', cursor);
    }
    return `/api/v1/events/?${params.toString()}`;
}

function formatPrice(price: number, currency: string): string {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(price));
}

export function EventsPage() {
    const [items, setItems] = useState<EventItem[]>([]);
    const [nextCursor, setNextCursor] = useState<string | null>(null);
    const [pending, setPending] = useState<boolean>(true);
    const [error, setError] = useState<string>('');
    const [query, setQuery] = useState<string>('');
    const [activeQuery, setActiveQuery] = useState<string>('');
    const [sortBy, setSortBy] = useState<SortKey>('start_at');

    const fetchEvents = async (q: string, cursor: string | null, append: boolean, sort: SortKey) => {
        setPending(true);
        setError('');
        try {
            const response = await publicApiFetch(buildEventsUrl(q, cursor, sort));
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
                const response = await publicApiFetch(buildEventsUrl('', null, 'start_at'));
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
        void fetchEvents(trimmed, null, false, sortBy);
    };

    const handleLoadMore = () => {
        if (!nextCursor) {
            return;
        }
        void fetchEvents(activeQuery, nextCursor, true, sortBy);
    };

    const handleSort = (next: SortKey) => {
        // NOTE: sorting only applies to browse mode; switching restarts pagination.
        if (pending || next === sortBy || activeQuery) {
            return;
        }
        setSortBy(next);
        setNextCursor(null);
        void fetchEvents('', null, false, next);
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
            <div className="sort-toggle">
                <span>Sort by:</span>
                <button
                    type="button"
                    className={sortBy === 'start_at' ? 'active' : ''}
                    disabled={pending || Boolean(activeQuery)}
                    onClick={() => handleSort('start_at')}
                >
                    Date
                </button>
                <button
                    type="button"
                    className={sortBy === 'price' ? 'active' : ''}
                    disabled={pending || Boolean(activeQuery)}
                    onClick={() => handleSort('price')}
                >
                    Price
                </button>
            </div>
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
                                {event.type} · {new Date(event.start_at).toLocaleString()} ·{' '}
                                {formatPrice(event.price, event.currency)}
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

import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiFetch, parseDetail, publicApiFetch } from './api';
import { useAuth } from './auth';

type TicketStatus = 'available' | 'reserved' | 'booked' | 'anonymous_booked';

interface Ticket {
    id: number;
    event_id: number;
    status: TicketStatus;
    reserved_at: string | null;
    booked_at: string | null;
}

interface EventDetail {
    id: number;
    name: string;
    description: string;
    type: string;
    start_at: string;
}

export function EventDetailsPage() {
    const { eventId } = useParams<{ eventId: string }>();
    const { authState } = useAuth();
    const [event, setEvent] = useState<EventDetail | null>(null);
    const [eventPending, setEventPending] = useState<boolean>(true);
    const [eventError, setEventError] = useState<string>('');
    const [tickets, setTickets] = useState<Ticket[]>([]);
    const [pending, setPending] = useState<boolean>(true);
    const [loadError, setLoadError] = useState<string>('');
    const [actionError, setActionError] = useState<Record<number, string>>({});
    const [actionPending, setActionPending] = useState<Record<number, boolean>>({});

    const loadTickets = useCallback(async () => {
        setPending(true);
        setLoadError('');
        try {
            const response = await publicApiFetch(`/api/v1/events/${eventId}/tickets/`);
            if (!response.ok) {
                setLoadError(await parseDetail(response));
                return;
            }
            setTickets((await response.json()) as Ticket[]);
        } catch (err) {
            setLoadError(err instanceof Error ? err.message : 'unknown error');
        } finally {
            setPending(false);
        }
    }, [eventId]);

    useEffect(() => {
        let cancelled = false;
        const run = async () => {
            try {
                const response = await publicApiFetch(`/api/v1/events/${eventId}/tickets/`);
                if (cancelled) {
                    return;
                }
                if (!response.ok) {
                    setLoadError(await parseDetail(response));
                    return;
                }
                setTickets((await response.json()) as Ticket[]);
            } catch (err) {
                if (!cancelled) {
                    setLoadError(err instanceof Error ? err.message : 'unknown error');
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
    }, [eventId]);

    useEffect(() => {
        let cancelled = false;
        const run = async () => {
            setEventPending(true);
            setEventError('');
            try {
                const response = await publicApiFetch(`/api/v1/events/${eventId}`);
                if (cancelled) {
                    return;
                }
                if (!response.ok) {
                    setEventError(await parseDetail(response));
                    return;
                }
                setEvent((await response.json()) as EventDetail);
            } catch (err) {
                if (!cancelled) {
                    setEventError(err instanceof Error ? err.message : 'unknown error');
                }
            } finally {
                if (!cancelled) {
                    setEventPending(false);
                }
            }
        };
        void run();
        return () => {
            cancelled = true;
        };
    }, [eventId]);

    const handleAction = async (ticketId: number, action: 'reserve' | 'book') => {
        setActionError((prev) => ({ ...prev, [ticketId]: '' }));
        setActionPending((prev) => ({ ...prev, [ticketId]: true }));
        try {
            const response = await apiFetch(`/api/v1/events/${eventId}/tickets/${ticketId}/${action}`, {
                method: 'POST',
            });
            if (!response.ok) {
                const detail = await parseDetail(response);
                setActionError((prev) => ({ ...prev, [ticketId]: detail }));
                return;
            }
            await loadTickets();
        } catch (err) {
            setActionError((prev) => ({
                ...prev,
                [ticketId]: err instanceof Error ? err.message : 'unknown error',
            }));
        } finally {
            setActionPending((prev) => ({ ...prev, [ticketId]: false }));
        }
    };

    const isSignedIn = authState === 'signed-in';

    return (
        <section>
            <p>
                <Link to="/events">← Back to events</Link>
            </p>
            {eventPending && !event && <h1>Loading…</h1>}
            {eventError && <p className="error">{eventError}</p>}
            {event && (
                <>
                    <h1>{event.name}</h1>
                    <p className="event-meta">
                        {event.type} · {new Date(event.start_at).toLocaleString()}
                    </p>
                    <p>{event.description}</p>
                </>
            )}
            {!isSignedIn && <p className="hint">Sign in to reserve or book tickets.</p>}
            {loadError && <p className="error">{loadError}</p>}
            {pending && tickets.length === 0 && <p>Loading…</p>}
            {!pending && tickets.length === 0 && !loadError && <p>No tickets for this event.</p>}
            {tickets.length > 0 && (
                <table className="tickets">
                    <thead>
                        <tr>
                            <th>Ticket</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tickets.map((ticket) => (
                            <tr key={ticket.id}>
                                <td>#{ticket.id}</td>
                                <td>{ticket.status}</td>
                                <td>
                                    <button
                                        type="button"
                                        disabled={!isSignedIn || actionPending[ticket.id]}
                                        onClick={() => void handleAction(ticket.id, 'reserve')}
                                    >
                                        Reserve
                                    </button>{' '}
                                    <button
                                        type="button"
                                        disabled={!isSignedIn || actionPending[ticket.id]}
                                        onClick={() => void handleAction(ticket.id, 'book')}
                                    >
                                        Book
                                    </button>
                                    {actionError[ticket.id] && <div className="error">{actionError[ticket.id]}</div>}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </section>
    );
}

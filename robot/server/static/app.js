// Restore state on load
fetch('/state')
    .then(r => r.json())
    .then(s => {
        document.getElementById('status').textContent = s.status || 'idle';
        try {
            document.getElementById('event').textContent = JSON.stringify(s.last_event, null, 2);
        } catch {
            document.getElementById('event').textContent = s.last_event || '-';
        }
        document.getElementById('time').textContent = s.last_time ? new Date(s.last_time).toLocaleString() : '-';
    });

// SSE updates
const es = new EventSource('/events');
es.onmessage = e => {
    const [status, event, time] = e.data.split(' | ');
    document.getElementById('status').textContent = status;
    try {
        document.getElementById('event').textContent = JSON.stringify(JSON.parse(event), null, 2);
    } catch {
        document.getElementById('event').textContent = event;
    }
    document.getElementById('time').textContent = new Date(time).toLocaleString();
};

// Manual trigger
function trigger(type) {
    fetch(`/trigger_${type}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({event: `manual_${type}`})
    });
}

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

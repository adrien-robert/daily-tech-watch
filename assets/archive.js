/* Daily Tech Watch: search box for the archive page.
   Every headline is already in the page; searching shows the days that have a
   matching headline and only the headlines that match. */

function sws_escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function sws_highlight(node, pattern) {
    const text = node.dataset.title;
    node.textContent = '';
    if (!pattern) {
        node.textContent = text;
        return;
    }
    let last = 0;
    for (const match of text.matchAll(pattern)) {
        node.append(text.slice(last, match.index));
        const mark = document.createElement('mark');
        mark.textContent = match[0];
        node.append(mark);
        last = match.index + match[0].length;
    }
    node.append(text.slice(last));
}

function sws_filterArchive(query) {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const pattern = words.length ? new RegExp(words.map(sws_escapeRegExp).join('|'), 'gi') : null;
    let days = 0;
    let hits = 0;
    document.querySelectorAll('.archive-month').forEach(month => {
        let monthVisible = 0;
        month.querySelectorAll('.archive-day').forEach(day => {
            let dayHits = 0;
            day.querySelectorAll('.archive-titles li[data-title]').forEach((li, index) => {
                const title = li.dataset.title.toLowerCase();
                const match = words.every(word => title.includes(word));
                li.hidden = words.length ? !match : index >= 3;
                if (words.length && match) dayHits += 1;
                sws_highlight(li, match ? pattern : null);
            });
            const more = day.querySelector('.archive-more');
            if (more) more.hidden = words.length > 0;
            day.hidden = words.length > 0 && dayHits === 0;
            if (!day.hidden) monthVisible += 1;
            hits += dayHits;
        });
        month.hidden = monthVisible === 0;
        days += monthVisible;
    });
    const status = document.getElementById('archiveStatus');
    if (status) {
        const total = status.dataset.total;
        status.textContent = words.length
            ? `${hits} headline${hits === 1 ? '' : 's'} in ${days} report${days === 1 ? '' : 's'}`
            : total;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('archiveSearch');
    if (!input) return;
    input.addEventListener('input', () => sws_filterArchive(input.value));
    sws_filterArchive(input.value);
});

/* Daily Tech Watch: tag filter for a report page.
   Buttons are built from the tags present on the page; picking one hides the
   other items and any category left empty. */

const SWS_TAG_LABELS = {
    security: '🔒 Security',
    breaking: '⚠️ Breaking',
    deadline: '⏰ Deadline',
    important: '❗ Important',
    new: '🆕 New',
    update: '🔄 Update',
    milestone: '🎯 Milestone',
    tool: '🔧 Tool',
    trend: '📈 Trend',
    tutorial: '📚 Tutorial'
};

function sws_makeFilterButton(label, tag, count) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = tag ? 'filter-btn' : 'filter-btn filter-btn-all';
    btn.setAttribute('aria-pressed', tag ? 'false' : 'true');
    btn.append(label);
    if (tag) {
        btn.dataset.tag = tag;
        const badge = document.createElement('span');
        badge.className = 'filter-count';
        badge.textContent = count;
        btn.append(badge);
    }
    btn.addEventListener('click', () => sws_filterByTag(tag));
    return btn;
}

function sws_initFilters() {
    const bar = document.getElementById('filterBar');
    if (!bar) return;
    const counts = {};
    document.querySelectorAll('article.item').forEach(item => {
        counts[item.dataset.tag] = (counts[item.dataset.tag] || 0) + 1;
    });
    const tags = Object.keys(SWS_TAG_LABELS).filter(tag => counts[tag]);
    if (tags.length < 2) return;
    bar.append(sws_makeFilterButton('All', null));
    tags.forEach(tag => bar.append(sws_makeFilterButton(SWS_TAG_LABELS[tag], tag, counts[tag])));
    bar.hidden = false;
}

function sws_filterByTag(activeTag) {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.setAttribute('aria-pressed', String((btn.dataset.tag || null) === activeTag));
    });
    document.querySelectorAll('details.category').forEach(category => {
        const items = category.querySelectorAll('article.item');
        let visible = 0;
        items.forEach(item => {
            item.hidden = activeTag !== null && item.dataset.tag !== activeTag;
            if (!item.hidden) visible += 1;
        });
        category.hidden = visible === 0;
        if (visible > 0 && activeTag !== null) category.open = true;
        const count = category.querySelector('.category-count');
        if (count) {
            const total = items.length;
            const noun = total === 1 ? 'item' : 'items';
            count.textContent = activeTag === null ? `${total} ${noun}` : `${visible} of ${total} ${noun}`;
        }
    });
}

document.addEventListener('DOMContentLoaded', sws_initFilters);

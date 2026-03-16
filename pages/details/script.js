function toggleEdit() {
    const form = document.getElementById('editForm');
    const view = document.querySelector('.details-grid');
    if (form.style.display === 'none' || form.style.display === '') {
        form.style.display = 'block';
        view.style.opacity = '0.5'; // Затемняем просмотр
        view.style.pointerEvents = 'none';
        window.scrollTo(0, document.body.scrollHeight);
    } else {
        form.style.display = 'none';
        view.style.opacity = '1';
        view.style.pointerEvents = 'auto';
    }
}

function toggleWorkFields(select) {
    const fields = document.getElementById('editWorkFields');
    if (select.value === 'В работе') {
        fields.style.display = 'block';
    } else {
        fields.style.display = 'none';
    }
}
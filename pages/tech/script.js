function toggleWorkFields(select) {
    const fields = document.getElementById('workFields');
    fields.style.display = select.value === 'В работе' ? 'block' : 'none';
}
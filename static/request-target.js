// Standalone objects are used only for firewall installations.
document.querySelectorAll('[data-request-target-form]').forEach((form) => {
  const target = form.querySelector('[name="target_kind"]');
  const objects = form.querySelector('[data-request-objects]');
  if (!target || !objects) return;
  const update = () => {
    const feeds = target.value === 'threat_feeds';
    objects.disabled = feeds;
    objects.hidden = feeds;
    const source = objects.querySelector('select[name="objects"]');
    if (source) {
      source.disabled = feeds;
      source.dispatchEvent(new Event('change', {bubbles: true}));
    }
  };
  target.addEventListener('change', update);
  update();
});

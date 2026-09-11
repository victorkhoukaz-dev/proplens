/* Keep tracker action menus compact: one open menu at a time. */
(() => {
  const menuSelector = '.row-more, .tracked-parlay-actions details';
  const openSelector = '.row-more[open], .tracked-parlay-actions details[open]';

  function closeMenus(except = null) {
    document.querySelectorAll(openSelector).forEach(menu => {
      if (menu !== except) menu.removeAttribute('open');
    });
  }

  document.addEventListener('toggle', event => {
    const menu = event.target;
    if (!(menu instanceof HTMLDetailsElement) || !menu.matches(menuSelector) || !menu.open) return;
    closeMenus(menu);
  }, true);

  document.addEventListener('click', event => {
    if (!event.target.closest(menuSelector)) closeMenus();
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeMenus();
  });
})();

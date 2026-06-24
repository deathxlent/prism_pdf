function initApp() {
    initNav();
    initDocumentsPage();
}

function initNav() {
    const navItems = $$('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const href = item.querySelector('a').getAttribute('href');
            
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            if (href === '#/home' || href === '#home') {
                backToHome();
            }
        });
    });

    const homeNav = $$('.nav-item')[0];
    if (homeNav) homeNav.classList.add('active');
}

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

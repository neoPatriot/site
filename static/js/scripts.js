document.addEventListener('DOMContentLoaded', function() {
    const header = document.querySelector('header');
    if (!header) return;

    // We get the height once, assuming it doesn't change.
    const headerHeight = header.offsetHeight;
    const scrollThreshold = 10; // A small buffer

    const handleScroll = () => {
        if (window.scrollY > scrollThreshold) {
            if (!header.classList.contains('fixed-header')) {
                header.classList.add('fixed-header');
                document.body.style.paddingTop = headerHeight + 'px';
            }
        } else {
            if (header.classList.contains('fixed-header')) {
                header.classList.remove('fixed-header');
                document.body.style.paddingTop = '0';
            }
        }
    };

    // Listen for the scroll event
    window.addEventListener('scroll', handleScroll);

    // Run on page load as well in case the page is reloaded mid-scroll
    handleScroll();
});
